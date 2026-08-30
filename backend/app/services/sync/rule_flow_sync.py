"""Rule ↔ Flow bidirectional sync.

When a rule is updated we rebuild the matching check-node configs in every
flow whose check node was generated from that rule. When a flow node is
edited in the builder we mirror the change back to the originating rule.

The link is the `rule_id` field stamped on a check node's `config` by the
flow generator (see `app/services/nl_flow_generator/generator.py`).

A `contextvars`-based recursion guard prevents echo updates from looping.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.flow import DQFlow
from app.models.rule import DQRule

logger = logging.getLogger(__name__)

# Recursion guard — set while a sync is in progress so the opposite hook
# (e.g. a flow update triggered by a rule edit) does not loop back.
_IN_SYNC: contextvars.ContextVar[bool] = contextvars.ContextVar("_rule_flow_in_sync", default=False)


@contextmanager
def _sync_lock():
    token = _IN_SYNC.set(True)
    try:
        yield
    finally:
        _IN_SYNC.reset(token)


def is_syncing() -> bool:
    return _IN_SYNC.get()


# Fields on the check-node config that map back to rule fields.
_NODE_KEYS = (
    "ruleName",
    "rule_name",
    "description",
    "severity",
    "subtype",
    "columns",
    "threshold_pass",
    "threshold_warn",
    "null_handling",
    "filter_expression",
)


# ---------------------------------------------------------------------------
# Rule → Flow
# ---------------------------------------------------------------------------


def _rule_to_node_config_overrides(rule: DQRule) -> dict[str, Any]:
    """Compute the fields the rule update should push into matching nodes."""
    meta = rule.meta_data or {}
    check_cfg = meta.get("check_config") or {}
    canonical = rule.canonical_rule or {}
    params = canonical.get("parameters") or {}
    thresh = rule.threshold_config or {}

    overrides: dict[str, Any] = {
        "ruleName": rule.name,
        "rule_name": rule.name,
        "description": rule.description or "",
        "severity": (canonical.get("severity") or check_cfg.get("severity") or "major"),
        "subtype": (check_cfg.get("subtype") or rule.rule_type or params.get("subtype")),
        "columns": (
            check_cfg.get("columns")
            or list(rule.target_columns or [])
            or params.get("columns")
            or []
        ),
        "threshold_pass": (
            check_cfg.get("threshold_pass")
            if check_cfg.get("threshold_pass") is not None
            else thresh.get("pass_threshold")
        ),
        "threshold_warn": (
            check_cfg.get("threshold_warn")
            if check_cfg.get("threshold_warn") is not None
            else thresh.get("warning_threshold")
        ),
        "null_handling": check_cfg.get("null_handling") or params.get("null_handling"),
        "filter_expression": (
            check_cfg.get("filter_expression") or params.get("filter_expression")
        ),
    }
    # Drop keys whose value is None so we never wipe a node field by accident.
    return {k: v for k, v in overrides.items() if v is not None}


def propagate_rule_to_flows(
    db: Session,
    workspace_id: UUID,
    rule: DQRule,
) -> int:
    """Apply rule changes to every flow node linked to this rule.

    Returns the count of flows that were updated. Best-effort: a failure on
    one flow is logged but does not abort the others.
    """
    if is_syncing():
        return 0

    overrides = _rule_to_node_config_overrides(rule)
    rule_id_str = str(rule.id)
    affected = 0

    # JSONB containment query: find flows whose definition references rule_id.
    flows = (
        db.query(DQFlow)
        .filter(
            and_(
                DQFlow.workspace_id == workspace_id,
                DQFlow.flow_definition["nodes"].astext.ilike(f"%{rule_id_str}%"),
            )
        )
        .all()
    )

    with _sync_lock():
        for flow in flows:
            try:
                definition = flow.flow_definition or {}
                nodes = definition.get("nodes") or []
                changed = False
                for node in nodes:
                    if node.get("type") != "check":
                        continue
                    cfg = node.get("config") or {}
                    if str(cfg.get("rule_id") or "") != rule_id_str:
                        continue
                    for k, v in overrides.items():
                        if cfg.get(k) != v:
                            cfg[k] = v
                            changed = True
                    # Refresh node label too.
                    new_label = rule.name
                    if new_label and node.get("label") != new_label:
                        node["label"] = new_label
                        changed = True
                    node["config"] = cfg
                if changed:
                    flow.flow_definition = definition
                    flag_modified(flow, "flow_definition")
                    flow.version = (flow.version or 1) + 1
                    affected += 1
            except Exception:
                logger.exception(
                    "rule_to_flow_sync_failed rule_id=%s flow_id=%s",
                    rule_id_str,
                    flow.id,
                )
        if affected:
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("rule_to_flow_sync_commit_failed rule_id=%s", rule_id_str)
                return 0

    if affected:
        logger.info("rule_to_flow_sync rule_id=%s flows_updated=%d", rule_id_str, affected)
    return affected


# ---------------------------------------------------------------------------
# Flow → Rule
# ---------------------------------------------------------------------------

_SEVERITY_TO_BACKEND = {
    "blocker": "blocker",
    "critical": "critical",
    "high": "major",
    "medium": "major",
    "major": "major",
    "low": "minor",
    "minor": "minor",
    "info": "info",
}


def _node_to_rule_patch(
    cfg: dict[str, Any],
    rule: DQRule,
) -> dict[str, Any]:
    """Build a dict of rule fields to update from a check-node config."""
    patch: dict[str, Any] = {}
    name = cfg.get("ruleName") or cfg.get("rule_name")
    if name and name != rule.name:
        patch["name"] = name
    desc = cfg.get("description")
    if desc is not None and desc != (rule.description or ""):
        patch["description"] = desc
    subtype = cfg.get("subtype")
    if subtype and subtype != rule.rule_type:
        patch["rule_type"] = subtype
    columns = cfg.get("columns")
    if columns is not None and list(columns) != list(rule.target_columns or []):
        patch["target_columns"] = list(columns)

    # Severity → canonical_rule.severity (backend enum).
    sev = cfg.get("severity")
    if sev:
        backend_sev = _SEVERITY_TO_BACKEND.get(str(sev).lower(), "major")
        current_sev = (rule.canonical_rule or {}).get("severity")
        if backend_sev != current_sev:
            new_cr = dict(rule.canonical_rule or {})
            new_cr["severity"] = backend_sev
            patch["canonical_rule"] = new_cr

    # Thresholds.
    tpass = cfg.get("threshold_pass")
    twarn = cfg.get("threshold_warn")
    if tpass is not None or twarn is not None:
        current = rule.threshold_config or {}
        new_thresh = dict(current)
        if tpass is not None and current.get("pass_threshold") != tpass:
            new_thresh["pass_threshold"] = tpass
        if twarn is not None and current.get("warning_threshold") != twarn:
            new_thresh["warning_threshold"] = twarn
        if new_thresh != current:
            patch["threshold_config"] = new_thresh

    return patch


def _extract_check_nodes(definition: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map node_id → config for every check node carrying a rule_id."""
    out: dict[str, dict[str, Any]] = {}
    if not definition:
        return out
    for node in definition.get("nodes") or []:
        if node.get("type") != "check":
            continue
        cfg = node.get("config") or {}
        rid = cfg.get("rule_id")
        if rid:
            out[node.get("id") or str(rid)] = cfg
    return out


def propagate_flow_to_rules(
    db: Session,
    workspace_id: UUID,
    old_definition: dict[str, Any] | None,
    new_definition: dict[str, Any] | None,
) -> int:
    """Mirror check-node config edits back to the originating rules.

    Returns the count of rules that were updated.
    """
    if is_syncing():
        return 0

    old_nodes = _extract_check_nodes(old_definition)
    new_nodes = _extract_check_nodes(new_definition)
    if not new_nodes:
        return 0

    affected = 0
    with _sync_lock():
        for node_id, new_cfg in new_nodes.items():
            rule_id_raw = new_cfg.get("rule_id")
            if not rule_id_raw:
                continue
            try:
                rule_uuid = UUID(str(rule_id_raw))
            except (TypeError, ValueError):
                continue

            rule = (
                db.query(DQRule)
                .filter(
                    and_(
                        DQRule.id == rule_uuid,
                        DQRule.workspace_id == workspace_id,
                    )
                )
                .first()
            )
            if not rule:
                continue

            # Skip nodes whose config did not change.
            if old_nodes.get(node_id) == new_cfg:
                continue

            patch = _node_to_rule_patch(new_cfg, rule)
            if not patch:
                continue

            try:
                _apply_patch_to_rule(rule, patch)
                rule.meta_data = _merge_check_config_into_meta(rule.meta_data, new_cfg)
                flag_modified(rule, "meta_data")
                affected += 1
            except Exception:
                logger.exception(
                    "flow_to_rule_sync_failed rule_id=%s node_id=%s",
                    rule_uuid,
                    node_id,
                )

        if affected:
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("flow_to_rule_sync_commit_failed")
                return 0

    if affected:
        logger.info("flow_to_rule_sync rules_updated=%d", affected)
    return affected


def _apply_patch_to_rule(rule: DQRule, patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if key == "canonical_rule":
            rule.canonical_rule = value
            flag_modified(rule, "canonical_rule")
        elif key == "threshold_config":
            rule.threshold_config = value
            flag_modified(rule, "threshold_config")
        elif hasattr(rule, key):
            setattr(rule, key, value)


def _merge_check_config_into_meta(
    meta: dict[str, Any] | None,
    node_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Persist the latest node config into rule.meta_data.check_config so the
    rule-edit modal stays in sync with what the flow has."""
    meta = dict(meta or {})
    saved = dict(meta.get("check_config") or {})
    # Only mirror the canonical user-facing keys.
    for k in (
        "ruleName",
        "description",
        "severity",
        "subtype",
        "columns",
        "threshold_pass",
        "threshold_warn",
        "null_handling",
        "filter_expression",
    ):
        if k in node_cfg:
            # Map ruleName → ruleName for the modal (it reads check_config.ruleName).
            saved[k] = node_cfg[k]
    meta["check_config"] = saved
    meta["dq_check_subtype"] = node_cfg.get("subtype", meta.get("dq_check_subtype"))
    return meta
