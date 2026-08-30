"""
NL Rule Flow Generator — creates/updates flows from compiled check configs.
"""

from __future__ import annotations

import random
import string
import time
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.nl_compiler import CompiledCheckConfig
from app.schemas.nl_flow_generator import (
    GeneratedConnection,
    GeneratedNode,
    GenerateFlowRequest,
    GenerateFlowResponse,
)

# Layout constants
SOURCE_X = 100
CHECK_X = 400
Y_START = 100
Y_SPACING = 150


def _uid(prefix: str = "node") -> str:
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{ts}_{rand}"


class NLFlowGenerator:
    """Generate data quality flows from compiled check configs."""

    def generate(
        self,
        db: Session,
        workspace_id: UUID,
        user_id: UUID,
        request: GenerateFlowRequest,
    ) -> GenerateFlowResponse:
        if request.target_flow_id:
            return self._add_to_flow(db, workspace_id, user_id, request)
        return self._create_flow(db, workspace_id, user_id, request)

    # ── create new flow ──

    def _create_flow(
        self,
        db: Session,
        workspace_id: UUID,
        user_id: UUID,
        request: GenerateFlowRequest,
    ) -> GenerateFlowResponse:
        nodes: list[dict[str, Any]] = []
        connections: list[dict[str, Any]] = []
        generated_nodes: list[GeneratedNode] = []
        generated_connections: list[GeneratedConnection] = []

        # Deduplicate source nodes by dataset_id
        source_map: dict[str, str] = {}  # dataset_id → source_node_id
        source_y = Y_START

        for cfg in request.compiled_configs:
            ds_id = cfg.dataset_id or "default"
            if ds_id not in source_map:
                source_node_id = _uid("source")
                source_map[ds_id] = source_node_id
                ds_name = cfg.config.get("dataset_name")
                meta = self._load_dataset_metadata(db, ds_id)
                source_node = self._build_source_node(
                    source_node_id,
                    ds_id,
                    source_y,
                    dataset_name=ds_name,
                    dataset_meta=meta,
                )
                nodes.append(source_node)
                generated_nodes.append(
                    GeneratedNode(
                        node_id=source_node_id,
                        node_type="source",
                        label=source_node["label"],
                    )
                )
                source_y += Y_SPACING

        # Build check nodes
        check_y = Y_START
        for cfg in request.compiled_configs:
            ds_id = cfg.dataset_id or "default"
            source_node_id = source_map[ds_id]
            check_node_id = _uid("check")
            check_node = self._build_check_node(
                check_node_id,
                cfg,
                check_y,
                request,
            )
            nodes.append(check_node)
            generated_nodes.append(
                GeneratedNode(
                    node_id=check_node_id,
                    node_type="check",
                    label=check_node["label"],
                )
            )

            # Connection
            conn_id = _uid("conn")
            conn = {
                "id": conn_id,
                "from": source_node_id,
                "to": check_node_id,
                "sourcePort": "output",
                "targetPort": "input",
            }
            connections.append(conn)
            generated_connections.append(
                GeneratedConnection(
                    connection_id=conn_id,
                    source_node=source_node_id,
                    target_node=check_node_id,
                )
            )
            check_y += Y_SPACING

        # Build flow definition
        flow_def = {
            "nodes": nodes,
            "connections": connections,
            "metadata": {
                "generated_by": "nl_rule_flow_generator",
                "nl_rule_text": request.nl_rule_text,
                "parse_request_id": request.parse_request_id,
            },
        }

        # Persist
        flow_name = request.flow_name or f"NL Rule Flow {int(time.time())}"
        flow = self._persist_flow(
            db,
            workspace_id,
            user_id,
            flow_name,
            request.flow_description,
            flow_def,
        )

        return GenerateFlowResponse(
            flow_id=str(flow.id),
            flow_name=flow.name,
            status=flow.status,
            nodes=generated_nodes,
            connections=generated_connections,
            is_new_flow=True,
        )

    # ── add to existing flow ──

    def _add_to_flow(
        self,
        db: Session,
        workspace_id: UUID,
        user_id: UUID,
        request: GenerateFlowRequest,
    ) -> GenerateFlowResponse:
        from app.models.flow import DQFlow

        flow = (
            db.query(DQFlow)
            .filter(
                DQFlow.id == request.target_flow_id,
                DQFlow.workspace_id == workspace_id,
            )
            .first()
        )

        if not flow:
            raise ValueError(f"Flow {request.target_flow_id} not found in workspace {workspace_id}")

        flow_def = flow.flow_definition or {"nodes": [], "connections": [], "metadata": {}}
        existing_nodes = flow_def.get("nodes", [])
        existing_connections = flow_def.get("connections", [])
        generated_nodes: list[GeneratedNode] = []
        generated_connections: list[GeneratedConnection] = []

        # Find max Y from existing nodes
        max_y = Y_START
        for n in existing_nodes:
            pos = n.get("position", {})
            ny = pos.get("y", 0)
            if ny >= max_y:
                max_y = ny + Y_SPACING

        # Build source map from existing source nodes
        source_map: dict[str, str] = {}
        for n in existing_nodes:
            if n.get("type") == "source":
                ds_id = n.get("config", {}).get("dataset_id")
                if ds_id:
                    source_map[ds_id] = n["id"]

        check_y = max_y
        for cfg in request.compiled_configs:
            ds_id = cfg.dataset_id or "default"

            # Create source node if not found
            if ds_id not in source_map:
                source_node_id = _uid("source")
                source_map[ds_id] = source_node_id
                ds_name = cfg.config.get("dataset_name")
                meta = self._load_dataset_metadata(db, ds_id)
                source_node = self._build_source_node(
                    source_node_id,
                    ds_id,
                    check_y,
                    dataset_name=ds_name,
                    dataset_meta=meta,
                )
                existing_nodes.append(source_node)
                generated_nodes.append(
                    GeneratedNode(
                        node_id=source_node_id,
                        node_type="source",
                        label=source_node["label"],
                    )
                )

            source_node_id = source_map[ds_id]
            check_node_id = _uid("check")
            check_node = self._build_check_node(check_node_id, cfg, check_y, request)
            existing_nodes.append(check_node)
            generated_nodes.append(
                GeneratedNode(
                    node_id=check_node_id,
                    node_type="check",
                    label=check_node["label"],
                )
            )

            conn_id = _uid("conn")
            conn = {
                "id": conn_id,
                "from": source_node_id,
                "to": check_node_id,
                "sourcePort": "output",
                "targetPort": "input",
            }
            existing_connections.append(conn)
            generated_connections.append(
                GeneratedConnection(
                    connection_id=conn_id,
                    source_node=source_node_id,
                    target_node=check_node_id,
                )
            )
            check_y += Y_SPACING

        # Update flow
        flow_def["nodes"] = existing_nodes
        flow_def["connections"] = existing_connections
        flow.flow_definition = flow_def
        flow.version = (flow.version or 1) + 1
        db.commit()
        db.refresh(flow)

        return GenerateFlowResponse(
            flow_id=str(flow.id),
            flow_name=flow.name,
            status=flow.status,
            nodes=generated_nodes,
            connections=generated_connections,
            is_new_flow=False,
        )

    # ── node builders ──

    def _load_dataset_metadata(
        self,
        db: Session,
        dataset_id: str,
    ) -> dict[str, Any]:
        """Look up the source dataset's data_source_id, schema, table and field list
        so that the generated source node carries everything the UI canvas and
        executor need (data_source_id, schema_name, table_name, metadata.columns).
        Returns an empty dict when the dataset cannot be resolved."""
        if not dataset_id or dataset_id == "default":
            return {}
        try:
            row = db.execute(
                text(
                    "SELECT data_source_id, schema_name, physical_identifier, dataset_name "
                    "FROM control.datasets WHERE dataset_id = CAST(:dsid AS UUID) "
                    "AND archived_at IS NULL"
                ),
                {"dsid": str(dataset_id)},
            ).first()
            if not row:
                return {}
            field_rows = db.execute(
                text(
                    "SELECT field_name, data_type FROM control.dataset_fields "
                    "WHERE dataset_id = CAST(:dsid AS UUID) ORDER BY ordinal_position ASC"
                ),
                {"dsid": str(dataset_id)},
            ).fetchall()
            columns = [{"name": fr[0], "type": fr[1]} for fr in field_rows if fr[0]]
            return {
                "data_source_id": str(row[0]) if row[0] else None,
                "schema_name": row[1],
                "table_name": row[2],
                "dataset_name": row[3],
                "columns": columns,
            }
        except Exception:
            # Best-effort enrichment — never fail flow creation on metadata lookup.
            return {}

    def _build_source_node(
        self,
        node_id: str,
        dataset_id: str,
        y: int,
        dataset_name: str | None = None,
        dataset_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = dataset_meta or {}
        display = dataset_name or meta.get("dataset_name") or dataset_id
        config: dict[str, Any] = {"name": display}
        if dataset_id and dataset_id != "default":
            config["dataset_id"] = dataset_id
        if dataset_name:
            config["dataset_name"] = dataset_name
        elif meta.get("dataset_name"):
            config["dataset_name"] = meta["dataset_name"]
        # Physical-source fields required by check executor + UI canvas.
        if meta.get("data_source_id"):
            config["data_source_id"] = meta["data_source_id"]
            config["source_type"] = "table"
        if meta.get("schema_name"):
            config["schema_name"] = meta["schema_name"]
        if meta.get("table_name"):
            config["table_name"] = meta["table_name"]
        cols = meta.get("columns") or []
        if cols:
            config["columns"] = cols
            config["metadata"] = {
                "columns": cols,
                "schema_name": meta.get("schema_name"),
                "table_name": meta.get("table_name"),
            }
        return {
            "id": node_id,
            "type": "source",
            "label": f"Source: {display[:30]}",
            "config": config,
            "position": {"x": SOURCE_X, "y": y},
        }

    def _build_check_node(
        self,
        node_id: str,
        cfg: CompiledCheckConfig,
        y: int,
        request: GenerateFlowRequest,
    ) -> dict[str, Any]:
        node_config = dict(cfg.config)
        node_config["subtype"] = cfg.subtype
        node_config["severity"] = cfg.severity
        node_config["ruleName"] = cfg.rule_name
        node_config["rule_name"] = cfg.rule_name
        # Link back to the originating rule when known. Enables rule↔flow
        # bidirectional sync (see backend/app/services/sync/rule_flow_sync.py).
        if cfg.rule_id:
            node_config["rule_id"] = cfg.rule_id
        if cfg.description:
            node_config["description"] = cfg.description
        if request.nl_rule_text:
            node_config["nl_rule_text"] = request.nl_rule_text
        if request.parse_request_id:
            node_config["parse_request_id"] = request.parse_request_id

        # Mirror form-field keys for the UI: schemas use snake_case, runtime
        # executor accepts camelCase. Emit both so the check-node config panel
        # is fully populated.
        _CAMEL_TO_SNAKE = {
            "allowedValues": "allowed_values",
            "caseSensitive": "case_sensitive",
            "minValue": "min_value",
            "maxValue": "max_value",
            "inclusiveMin": "inclusive_min",
            "inclusiveMax": "inclusive_max",
            "scopeColumns": "scope_columns",
            "fuzzyAlgorithm": "fuzzy_algorithm",
            "fuzzyThreshold": "fuzzy_threshold",
            "temporalColumn": "temporal_column",
            "temporalWindowValue": "temporal_window_value",
            "temporalWindowUnit": "temporal_window_unit",
            "minLength": "min_length",
            "maxLength": "max_length",
            "expectedCase": "expected_case",
            "allowedCharset": "allowed_charset",
            "standardName": "standard_name",
            "structuralPattern": "structural_pattern",
            "comparisonColumn": "comparison_column",
            "dateOperator": "date_operator",
            "referenceDataset": "reference_dataset",
            "referenceColumn": "reference_column",
            "businessRuleExpression": "business_rule_expression",
            "ruleExpression": "rule_expression",
            "groupByColumns": "group_by_columns",
            "startColumn": "start_column",
            "endColumn": "end_column",
            "aggregateFunction": "aggregate_function",
            "expectedColumn": "expected_column",
            "conditionColumn": "condition_column",
            "conditionOperator": "condition_operator",
            "conditionValue": "condition_value",
            "placeholderValues": "placeholder_values",
            "multiFieldMode": "multi_field_mode",
            "checkMode": "check_mode",
            "uniquenessMode": "uniqueness_mode",
            "validationType": "validation_type",
            "conformityType": "conformity_type",
            "consistencyType": "consistency_type",
        }
        for camel_key, snake_key in _CAMEL_TO_SNAKE.items():
            if camel_key in node_config and snake_key not in node_config:
                node_config[snake_key] = node_config[camel_key]

        return {
            "id": node_id,
            "type": "check",
            "checkType": cfg.check_type,
            "label": cfg.rule_name,
            "config": node_config,
            "position": {"x": CHECK_X, "y": y},
        }

    # ── persistence ──

    def _persist_flow(
        self,
        db: Session,
        workspace_id: UUID,
        user_id: UUID,
        name: str,
        description: str | None,
        flow_def: dict[str, Any],
    ):
        from app.models.flow import DQFlow

        flow = DQFlow(
            workspace_id=workspace_id,
            name=name,
            description=description or "Generated from NL rule builder",
            flow_definition=flow_def,
            status="draft",
            created_by=user_id,
            version=1,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        return flow
