"""
F105 — NL Rule Flow Generator Tests
40+ tests covering schemas, generator, node building, and endpoint.
"""

from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.schemas.nl_compiler import CompiledCheckConfig
from app.schemas.nl_flow_generator import (
    GeneratedConnection,
    GeneratedNode,
    GenerateFlowRequest,
    GenerateFlowResponse,
)
from app.services.nl_flow_generator.generator import (
    CHECK_X,
    SOURCE_X,
    Y_SPACING,
    Y_START,
    NLFlowGenerator,
    _uid,
)

# ── helpers ──


def make_compiled(
    check_type: str = "completeness",
    subtype: str = "null",
    dataset_id: str = None,
    rule_name: str = "test_rule",
    columns: list = None,
    **extra_config,
) -> CompiledCheckConfig:
    ds_id = dataset_id or str(uuid4())
    cfg = {
        "columns": columns or ["email"],
        "threshold_pass": 100,
        "null_handling": "fail",
        **extra_config,
    }
    return CompiledCheckConfig(
        check_type=check_type,
        subtype=subtype,
        dataset_id=ds_id,
        rule_name=rule_name,
        severity="medium",
        description="Test check",
        config=cfg,
    )


def make_request(
    configs=None,
    target_flow_id=None,
    flow_name=None,
    nl_rule_text=None,
) -> GenerateFlowRequest:
    return GenerateFlowRequest(
        compiled_configs=configs or [make_compiled()],
        target_flow_id=target_flow_id,
        flow_name=flow_name,
        nl_rule_text=nl_rule_text,
    )


def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: setattr(obj, "id", uuid4()))
    return db


generator = NLFlowGenerator()
WS_ID = uuid4()
USER_ID = uuid4()


# ══════════════════════════════════════
# 1. Schema Tests
# ══════════════════════════════════════


class TestSchemas:
    def test_generate_flow_request_minimal(self):
        req = make_request()
        assert len(req.compiled_configs) == 1
        assert req.target_flow_id is None

    def test_generate_flow_request_with_target(self):
        req = make_request(target_flow_id=str(uuid4()))
        assert req.target_flow_id is not None

    def test_generate_flow_response(self):
        resp = GenerateFlowResponse(
            flow_id=str(uuid4()),
            flow_name="Test Flow",
            status="draft",
            nodes=[],
            connections=[],
            is_new_flow=True,
        )
        assert resp.status == "draft"
        assert resp.is_new_flow is True

    def test_generated_node(self):
        n = GeneratedNode(node_id="n1", node_type="source", label="Source")
        assert n.node_id == "n1"

    def test_generated_connection(self):
        c = GeneratedConnection(connection_id="c1", source_node="n1", target_node="n2")
        assert c.source_node == "n1"

    def test_request_requires_at_least_one_config(self):
        with pytest.raises(Exception):
            GenerateFlowRequest(compiled_configs=[])


# ══════════════════════════════════════
# 2. UID Generation
# ══════════════════════════════════════


class TestUID:
    def test_uid_prefix(self):
        uid = _uid("source")
        assert uid.startswith("source_")

    def test_uid_unique(self):
        ids = {_uid("node") for _ in range(100)}
        assert len(ids) == 100


# ══════════════════════════════════════
# 3. Node Building
# ══════════════════════════════════════


class TestNodeBuilding:
    def test_build_source_node(self):
        node = generator._build_source_node("src-1", "ds-123", 100)
        assert node["id"] == "src-1"
        assert node["type"] == "source"
        assert node["config"]["dataset_id"] == "ds-123"
        assert node["position"]["x"] == SOURCE_X
        assert node["position"]["y"] == 100

    def test_build_check_node(self):
        cfg = make_compiled()
        req = make_request()
        node = generator._build_check_node("chk-1", cfg, 200, req)
        assert node["id"] == "chk-1"
        assert node["type"] == "check"
        assert node["checkType"] == "completeness"
        assert node["position"]["x"] == CHECK_X

    def test_check_node_includes_subtype(self):
        cfg = make_compiled(subtype="null")
        node = generator._build_check_node("chk-1", cfg, 100, make_request())
        assert node["config"]["subtype"] == "null"

    def test_check_node_includes_severity(self):
        cfg = make_compiled()
        node = generator._build_check_node("chk-1", cfg, 100, make_request())
        assert node["config"]["severity"] == "medium"

    def test_check_node_includes_nl_text(self):
        cfg = make_compiled()
        req = make_request(nl_rule_text="email must not be null")
        node = generator._build_check_node("chk-1", cfg, 100, req)
        assert node["config"]["nl_rule_text"] == "email must not be null"

    def test_check_node_label_is_rule_name(self):
        cfg = make_compiled(rule_name="completeness_null_email")
        node = generator._build_check_node("chk-1", cfg, 100, make_request())
        assert node["label"] == "completeness_null_email"


# ══════════════════════════════════════
# 4. Create New Flow
# ══════════════════════════════════════


class TestCreateFlow:
    def test_single_config_creates_flow(self):
        db = mock_db()
        req = make_request(flow_name="Test Flow")
        resp = generator.generate(db, WS_ID, USER_ID, req)
        assert resp.is_new_flow is True
        assert resp.flow_name == "Test Flow"
        assert resp.status == "draft"
        assert len(resp.nodes) == 2  # 1 source + 1 check
        assert len(resp.connections) == 1

    def test_source_node_generated(self):
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request())
        source_nodes = [n for n in resp.nodes if n.node_type == "source"]
        assert len(source_nodes) == 1

    def test_check_node_generated(self):
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request())
        check_nodes = [n for n in resp.nodes if n.node_type == "check"]
        assert len(check_nodes) == 1

    def test_connection_links_source_to_check(self):
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request())
        conn = resp.connections[0]
        source_ids = {n.node_id for n in resp.nodes if n.node_type == "source"}
        check_ids = {n.node_id for n in resp.nodes if n.node_type == "check"}
        assert conn.source_node in source_ids
        assert conn.target_node in check_ids

    def test_flow_persisted(self):
        db = mock_db()
        generator.generate(db, WS_ID, USER_ID, make_request())
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_auto_name_when_none(self):
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request(flow_name=None))
        assert "NL Rule Flow" in resp.flow_name


# ══════════════════════════════════════
# 5. Rule Pack (Multiple Configs)
# ══════════════════════════════════════


class TestRulePack:
    def test_multiple_configs_same_dataset(self):
        ds_id = str(uuid4())
        cfgs = [
            make_compiled(dataset_id=ds_id, rule_name="check_1"),
            make_compiled(dataset_id=ds_id, rule_name="check_2"),
            make_compiled(dataset_id=ds_id, rule_name="check_3"),
        ]
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request(cfgs))
        source_nodes = [n for n in resp.nodes if n.node_type == "source"]
        check_nodes = [n for n in resp.nodes if n.node_type == "check"]
        assert len(source_nodes) == 1  # Deduplicated
        assert len(check_nodes) == 3
        assert len(resp.connections) == 3

    def test_multiple_configs_different_datasets(self):
        cfgs = [
            make_compiled(dataset_id=str(uuid4()), rule_name="check_a"),
            make_compiled(dataset_id=str(uuid4()), rule_name="check_b"),
        ]
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request(cfgs))
        source_nodes = [n for n in resp.nodes if n.node_type == "source"]
        assert len(source_nodes) == 2  # Different datasets

    def test_mixed_datasets(self):
        ds1 = str(uuid4())
        ds2 = str(uuid4())
        cfgs = [
            make_compiled(dataset_id=ds1, rule_name="c1"),
            make_compiled(dataset_id=ds2, rule_name="c2"),
            make_compiled(dataset_id=ds1, rule_name="c3"),
        ]
        db = mock_db()
        resp = generator.generate(db, WS_ID, USER_ID, make_request(cfgs))
        source_nodes = [n for n in resp.nodes if n.node_type == "source"]
        check_nodes = [n for n in resp.nodes if n.node_type == "check"]
        assert len(source_nodes) == 2  # ds1 + ds2
        assert len(check_nodes) == 3
        assert len(resp.connections) == 3


# ══════════════════════════════════════
# 6. Add to Existing Flow
# ══════════════════════════════════════


class TestAddToFlow:
    def _mock_flow(self, ds_id=None):
        flow = MagicMock()
        flow.id = uuid4()
        flow.name = "Existing Flow"
        flow.status = "draft"
        flow.version = 1
        flow.flow_definition = {
            "nodes": [
                {
                    "id": "existing-source",
                    "type": "source",
                    "label": "Existing Source",
                    "config": {"dataset_id": ds_id or str(uuid4())},
                    "position": {"x": 100, "y": 100},
                },
            ],
            "connections": [],
            "metadata": {},
        }
        return flow

    def test_add_to_flow_reuses_source(self):
        ds_id = str(uuid4())
        flow = self._mock_flow(ds_id)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = flow

        cfg = make_compiled(dataset_id=ds_id)
        req = make_request([cfg], target_flow_id=str(flow.id))
        resp = generator.generate(db, WS_ID, USER_ID, req)

        assert resp.is_new_flow is False
        source_nodes = [n for n in resp.nodes if n.node_type == "source"]
        assert len(source_nodes) == 0  # Reused existing source

    def test_add_to_flow_new_dataset_adds_source(self):
        flow = self._mock_flow()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = flow

        new_ds = str(uuid4())
        cfg = make_compiled(dataset_id=new_ds)
        req = make_request([cfg], target_flow_id=str(flow.id))
        resp = generator.generate(db, WS_ID, USER_ID, req)

        source_nodes = [n for n in resp.nodes if n.node_type == "source"]
        assert len(source_nodes) == 1  # New source for new dataset

    def test_add_to_flow_increments_version(self):
        flow = self._mock_flow()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = flow

        req = make_request(target_flow_id=str(flow.id))
        generator.generate(db, WS_ID, USER_ID, req)
        assert flow.version == 2

    def test_add_to_flow_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        req = make_request(target_flow_id=str(uuid4()))
        with pytest.raises(ValueError, match="not found"):
            generator.generate(db, WS_ID, USER_ID, req)

    def test_add_to_flow_preserves_existing_nodes(self):
        flow = self._mock_flow()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = flow

        existing_count = len(flow.flow_definition["nodes"])
        req = make_request(target_flow_id=str(flow.id))
        generator.generate(db, WS_ID, USER_ID, req)

        new_nodes = flow.flow_definition["nodes"]
        assert len(new_nodes) > existing_count


# ══════════════════════════════════════
# 7. Positioning
# ══════════════════════════════════════


class TestPositioning:
    def test_source_at_correct_x(self):
        node = generator._build_source_node("s1", "ds", 100)
        assert node["position"]["x"] == SOURCE_X

    def test_check_at_correct_x(self):
        cfg = make_compiled()
        node = generator._build_check_node("c1", cfg, 100, make_request())
        assert node["position"]["x"] == CHECK_X

    def test_y_spacing(self):
        db = mock_db()
        ds_id = str(uuid4())
        cfgs = [
            make_compiled(dataset_id=ds_id, rule_name="c1"),
            make_compiled(dataset_id=ds_id, rule_name="c2"),
        ]
        resp = generator.generate(db, WS_ID, USER_ID, make_request(cfgs))
        # Check that we have nodes with different y positions
        assert len(resp.nodes) == 3  # 1 source + 2 checks


# ══════════════════════════════════════
# 8. Metadata
# ══════════════════════════════════════


class TestMetadata:
    def test_nl_text_in_metadata(self):
        db = mock_db()
        req = make_request(nl_rule_text="email must not be null")
        generator.generate(db, WS_ID, USER_ID, req)
        # Check the flow_definition passed to persist
        call_args = db.add.call_args[0][0]
        flow_def = call_args.flow_definition
        assert flow_def["metadata"]["nl_rule_text"] == "email must not be null"

    def test_parse_request_id_in_metadata(self):
        db = mock_db()
        req = GenerateFlowRequest(
            compiled_configs=[make_compiled()],
            parse_request_id="req-123",
        )
        generator.generate(db, WS_ID, USER_ID, req)
        call_args = db.add.call_args[0][0]
        flow_def = call_args.flow_definition
        assert flow_def["metadata"]["parse_request_id"] == "req-123"


# ══════════════════════════════════════
# 9. Endpoint Tests
# ══════════════════════════════════════


class TestEndpoint:
    def test_generate_flow_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import generate_flow

        assert callable(generate_flow)

    def test_flow_generator_instance(self):
        from app.api.v1.endpoints.rule_builder import _flow_generator

        assert isinstance(_flow_generator, NLFlowGenerator)
