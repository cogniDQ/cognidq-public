"""
Unit Tests for Node Generator Utility
"""

import pytest
from app.services.llm.utils.node_generator import NodeGenerator


class TestNodeGenerator:
    """Test suite for NodeGenerator"""

    def setup_method(self):
        """Setup for each test"""
        self.generator = NodeGenerator()

    def test_create_completeness_check(self):
        """Test completeness check creation"""
        node = self.generator.create_completeness_check(
            columns=["email", "name"],
            threshold=95,
            source_node_id="source_123",
            position={"x": 400, "y": 100},
        )

        assert node["type"] == "check"
        assert node["checkType"] == "completeness"
        assert node["config"]["columns"] == ["email", "name"]
        assert node["config"]["threshold"] == 95
        assert node["config"]["checkForNull"] == True
        assert node["config"]["checkForEmpty"] == True
        assert node["sourceNodeId"] == "source_123"
        assert "Completeness Check" in node["name"]
        assert node["id"].startswith("check_completeness_")

    def test_create_validity_check_without_pattern(self):
        """Test validity check creation without pattern"""
        node = self.generator.create_validity_check(
            columns=["phone"],
            validation_type="phone",
            pattern=None,
            threshold=90,
            source_node_id="source_123",
            position={"x": 400, "y": 220},
        )

        assert node["config"]["validationType"] == "phone"
        assert "pattern" not in node["config"]

    def test_create_uniqueness_check(self):
        """Test uniqueness check creation"""
        node = self.generator.create_uniqueness_check(
            columns=["customer_id", "email"],
            threshold=100,
            source_node_id="source_123",
            position={"x": 400, "y": 340},
        )

        assert node["checkType"] == "uniqueness"
        assert node["config"]["columns"] == ["customer_id", "email"]
        assert node["config"]["threshold"] == 100
        assert "Uniqueness Check" in node["name"]

    def test_create_consistency_check(self):
        """Test consistency check creation"""
        node = self.generator.create_consistency_check(
            source_a_id="source_123",
            source_b_id="source_456",
            match_columns={"customer_id": "cust_id"},
            threshold=100,
            position={"x": 600, "y": 200},
        )

        assert node["checkType"] == "consistency"
        assert node["config"]["sourceA"] == "source_123"
        assert node["config"]["sourceB"] == "source_456"
        assert node["config"]["matchColumns"] == {"customer_id": "cust_id"}
        assert node["sourceNodeId"] is None  # Multi-source check

    def test_create_reconciliation_check(self):
        """Test reconciliation check creation"""
        node = self.generator.create_reconciliation_check(
            source_a_id="source_123",
            source_b_id="source_456",
            match_columns={"email": "email_address"},
            threshold=95,
            position={"x": 600, "y": 320},
        )

        assert node["checkType"] == "reconciliation"
        assert node["config"]["sourceA"] == "source_123"
        assert node["config"]["sourceB"] == "source_456"
        assert node["config"]["comparisonType"] == "exact_match"
        assert node["config"]["reportMismatches"] == True

    def test_create_conformity_check(self):
        """Test conformity check creation"""
        node = self.generator.create_conformity_check(
            columns=["postal_code"],
            format_spec="US Postal Code",
            threshold=90,
            source_node_id="source_123",
            position={"x": 400, "y": 460},
        )

        assert node["checkType"] == "conformity"
        assert node["config"]["format"] == "US Postal Code"
        assert "Conformity Check" in node["name"]

    def test_create_accuracy_check(self):
        """Test accuracy check creation"""
        node = self.generator.create_accuracy_check(
            columns=["balance"],
            reference_source="reference_db",
            threshold=95,
            source_node_id="source_123",
            position={"x": 400, "y": 580},
        )

        assert node["checkType"] == "accuracy"
        assert node["config"]["referenceSource"] == "reference_db"

    def test_create_timeliness_check(self):
        """Test timeliness check creation"""
        node = self.generator.create_timeliness_check(
            date_column="last_updated",
            max_age_days=7,
            threshold=90,
            source_node_id="source_123",
            position={"x": 400, "y": 700},
        )

        assert node["checkType"] == "timeliness"
        assert node["config"]["dateColumn"] == "last_updated"
        assert node["config"]["maxAgeDays"] == 7
        assert "Timeliness Check" in node["name"]

    def test_create_generic_check(self):
        """Test generic check creation"""
        custom_config = {"customField": "value", "threshold": 85}

        node = self.generator.create_generic_check(
            check_type="custom_check",
            config=custom_config,
            source_node_id="source_123",
            position={"x": 400, "y": 820},
        )

        assert node["checkType"] == "custom_check"
        assert node["config"] == custom_config
        assert "Custom_Check Check" in node["name"]

    def test_node_id_uniqueness(self):
        """Test that generated node IDs are unique"""
        nodes = []
        for i in range(10):
            node = self.generator.create_source_node(
                data_source_id=f"ds_{i}",
                name=f"Source {i}",
                table_name=f"table_{i}",
                columns=["id"],
                position={"x": 100, "y": 100},
            )
            nodes.append(node)

        # All IDs should be unique
        ids = [n["id"] for n in nodes]
        assert len(ids) == len(set(ids))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
