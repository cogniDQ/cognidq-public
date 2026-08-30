"""
Unit Tests for Flow Validator Utility
"""

import pytest
from app.services.llm.utils.validation import FlowValidator


class TestFlowValidator:
    """Test suite for FlowValidator"""

    def setup_method(self):
        """Setup for each test"""
        self.validator = FlowValidator()

    def test_validate_flow_structure_success(self):
        """Test flow validation - success case"""
        source_nodes = [
            {
                "id": "source_1",
                "type": "source",
                "config": {"tableName": "customers", "columns": ["id", "email"]},
            }
        ]

        check_nodes = [
            {
                "id": "check_1",
                "type": "check",
                "checkType": "completeness",
                "config": {"columns": ["email"], "threshold": 90},
            }
        ]

        connections = [{"id": "conn_1", "from": "source_1", "to": "check_1"}]

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert result["valid"] == True
        assert len(result["errors"]) == 0

    def test_validate_unconnected_check(self):
        """Test validation of unconnected check node"""
        source_nodes = [{"id": "source_1", "config": {"tableName": "test", "columns": []}}]
        check_nodes = [{"id": "check_1", "checkType": "completeness", "config": {"threshold": 90}}]
        connections = []

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert result["valid"] == False
        assert len(result["errors"]) > 0
        assert "no source connection" in result["errors"][0].lower()

    def test_validate_multi_source_check_no_connection_requirement(self):
        """Test that multi-source checks don't require sourceNodeId connection"""
        source_nodes = []
        check_nodes = [
            {
                "id": "check_1",
                "checkType": "reconciliation",
                "config": {"sourceA": "source_1", "sourceB": "source_2"},
            }
        ]
        connections = [{"from": "source_1", "to": "check_1"}, {"from": "source_2", "to": "check_1"}]

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        # Should be valid even though check has no sourceNodeId
        assert result["valid"] == True

    def test_validate_invalid_threshold_range(self):
        """Test validation of invalid threshold"""
        source_nodes = [{"id": "source_1", "config": {"tableName": "test", "columns": []}}]
        check_nodes = [
            {
                "id": "check_1",
                "checkType": "completeness",
                "config": {"threshold": 150},  # Invalid: > 100
            }
        ]
        connections = [{"from": "source_1", "to": "check_1"}]

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert result["valid"] == False
        assert any("threshold" in err.lower() for err in result["errors"])

    def test_validate_invalid_threshold_type(self):
        """Test validation of non-numeric threshold"""
        source_nodes = [{"id": "source_1", "config": {"tableName": "test", "columns": []}}]
        check_nodes = [
            {
                "id": "check_1",
                "checkType": "completeness",
                "config": {"threshold": "ninety"},  # Invalid: string
            }
        ]
        connections = [{"from": "source_1", "to": "check_1"}]

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert result["valid"] == False
        assert any("threshold" in err.lower() for err in result["errors"])

    def test_validate_missing_columns_warning(self):
        """Test warning for checks without columns"""
        source_nodes = [{"id": "source_1", "config": {"tableName": "test", "columns": ["id"]}}]
        check_nodes = [
            {
                "id": "check_1",
                "checkType": "completeness",
                "config": {"threshold": 90},  # No columns specified
            }
        ]
        connections = [{"from": "source_1", "to": "check_1"}]

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert len(result["warnings"]) > 0
        assert "no columns specified" in result["warnings"][0].lower()

    def test_validate_timeliness_check_no_columns_warning(self):
        """Test that timeliness check doesn't warn about missing columns"""
        source_nodes = [
            {"id": "source_1", "config": {"tableName": "test", "columns": ["created_at"]}}
        ]
        check_nodes = [
            {
                "id": "check_1",
                "checkType": "timeliness",
                "config": {"dateColumn": "created_at", "maxAgeDays": 30, "threshold": 90},
            }
        ]
        connections = [{"from": "source_1", "to": "check_1"}]

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        # Should not have warning about missing columns
        column_warnings = [w for w in result["warnings"] if "columns" in w.lower()]
        assert len(column_warnings) == 0

    def test_validate_missing_table_name(self):
        """Test validation of source without tableName"""
        source_nodes = [
            {
                "id": "source_1",
                "config": {"columns": ["id"]},  # Missing tableName
            }
        ]
        check_nodes = []
        connections = []

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert result["valid"] == False
        assert any("tableName" in err for err in result["errors"])

    def test_validate_source_no_columns_warning(self):
        """Test warning for source without columns"""
        source_nodes = [
            {
                "id": "source_1",
                "config": {"tableName": "customers"},  # No columns
            }
        ]
        check_nodes = []
        connections = []

        result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        assert len(result["warnings"]) > 0
        assert "no columns" in result["warnings"][0].lower()

    def test_detect_circular_dependency(self):
        """Test circular dependency detection"""
        connections = [
            {"from": "node_1", "to": "node_2"},
            {"from": "node_2", "to": "node_3"},
            {"from": "node_3", "to": "node_1"},  # Creates cycle
        ]

        has_cycle = self.validator._has_circular_dependencies(connections)
        assert has_cycle == True

    def test_no_circular_dependency(self):
        """Test no circular dependency in valid flow"""
        connections = [
            {"from": "source_1", "to": "check_1"},
            {"from": "source_1", "to": "check_2"},
            {"from": "source_2", "to": "check_1"},
        ]

        has_cycle = self.validator._has_circular_dependencies(connections)
        assert has_cycle == False

    def test_validate_check_config_completeness(self):
        """Test check config validation for completeness"""
        config = {"columns": ["email", "name"], "threshold": 90}

        result = self.validator.validate_check_config("completeness", config)
        assert result["valid"] == True
        assert len(result["errors"]) == 0

    def test_validate_check_config_missing_columns(self):
        """Test check config validation - missing columns"""
        config = {"threshold": 90}  # Missing columns

        result = self.validator.validate_check_config("completeness", config)
        assert result["valid"] == False
        assert any("columns" in err.lower() for err in result["errors"])

    def test_validate_check_config_validity(self):
        """Test check config validation for validity"""
        config = {"columns": ["email"], "validationType": "email", "threshold": 90}

        result = self.validator.validate_check_config("validity", config)
        assert result["valid"] == True

    def test_validate_check_config_validity_missing_type(self):
        """Test validity check validation - missing validationType"""
        config = {"columns": ["email"], "threshold": 90}

        result = self.validator.validate_check_config("validity", config)
        assert result["valid"] == False
        assert any("validationType" in err for err in result["errors"])

    def test_validate_check_config_reconciliation(self):
        """Test check config validation for reconciliation"""
        config = {"sourceA": "source_1", "sourceB": "source_2", "matchColumns": {"col1": "col2"}}

        result = self.validator.validate_check_config("reconciliation", config)
        assert result["valid"] == True

    def test_validate_check_config_reconciliation_missing_sources(self):
        """Test reconciliation check validation - missing sources"""
        config = {"matchColumns": {"col1": "col2"}}

        result = self.validator.validate_check_config("reconciliation", config)
        assert result["valid"] == False
        assert len(result["errors"]) >= 2  # Missing sourceA and sourceB

    def test_validate_check_config_timeliness(self):
        """Test check config validation for timeliness"""
        config = {"dateColumn": "created_at", "maxAgeDays": 30, "threshold": 90}

        result = self.validator.validate_check_config("timeliness", config)
        assert result["valid"] == True

    def test_validate_check_config_timeliness_missing_fields(self):
        """Test timeliness check validation - missing fields"""
        config = {"threshold": 90}

        result = self.validator.validate_check_config("timeliness", config)
        assert result["valid"] == False
        assert len(result["errors"]) == 2  # Missing dateColumn and maxAgeDays


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
