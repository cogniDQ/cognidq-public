"""
Node Generator Utility

Generates flow nodes with proper structure and IDs.
"""

import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class NodeGenerator:
    """Utility for generating flow nodes"""

    def create_source_node(
        self,
        data_source_id: str,
        name: str,
        table_name: str,
        columns: list[str],
        position: dict[str, int],
        schema_name: str | None = None,
        connection_type: str | None = None,
    ) -> dict[str, Any]:
        """Create a data source node"""
        # Build the full table path
        if schema_name and table_name:
            full_table_path = f"{schema_name}.{table_name}"
        else:
            full_table_path = table_name

        # Use snake_case field names for frontend display, but keep camelCase for backend validation
        config = {
            "id": data_source_id,  # Frontend checks for this to know if configured
            "dataSourceId": data_source_id,
            "name": name,  # Frontend checks for this too
            "displayPath": full_table_path,  # Show schema.table in UI
            "tableName": table_name,  # camelCase for backend validation
            "table_name": table_name,  # snake_case for frontend display
            "schema_name": schema_name if schema_name else "public",  # snake_case for frontend
            "type": connection_type
            if connection_type
            else "postgresql",  # 'type' not 'connectionType'
            "metadata": {"columns": columns},
        }

        node = {
            "id": f"source_{uuid4().hex[:12]}",
            "type": "source",
            "name": name,
            "config": config,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created source node: {node['id']} - {name} ({full_table_path})")
        return node

    def create_completeness_check(
        self, columns: list[str], threshold: int, source_node_id: str, position: dict[str, int]
    ) -> dict[str, Any]:
        """Create a completeness check node"""
        column_display = ", ".join(columns[:2])
        if len(columns) > 2:
            column_display += f" +{len(columns) - 2} more"

        node = {
            "id": f"check_completeness_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "completeness",
            "name": f"Completeness Check - {column_display}",
            "description": f"Checks that {', '.join(columns)} are not null or empty",
            "config": {
                "columns": columns,
                "threshold": threshold,
                "checkForNull": True,
                "checkForEmpty": True,
            },
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created completeness check: {node['id']}")
        return node

    def create_validity_check(
        self,
        columns: list[str],
        validation_type: str,
        pattern: str | None,
        threshold: int,
        source_node_id: str,
        position: dict[str, int],
    ) -> dict[str, Any]:
        """Create a validity check node"""
        config = {"columns": columns, "validationType": validation_type, "threshold": threshold}

        if pattern:
            config["pattern"] = pattern

        # Create name following the pattern: "Validity Check - column1, column2"
        columns_str = ", ".join(columns)

        node = {
            "id": f"check_validity_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "validity",
            "name": f"Validity Check - {columns_str}",
            "description": f"Validates {columns_str} format as {validation_type}",
            "config": config,
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created validity check: {node['id']} - {validation_type}")
        return node

    def create_uniqueness_check(
        self, columns: list[str], threshold: int, source_node_id: str, position: dict[str, int]
    ) -> dict[str, Any]:
        """Create a uniqueness check node"""
        node = {
            "id": f"check_uniqueness_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "uniqueness",
            "name": f"Uniqueness Check - {', '.join(columns)}",
            "description": f"Checks for duplicate values in {', '.join(columns)}",
            "config": {"columns": columns, "threshold": threshold},
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created uniqueness check: {node['id']}")
        return node

    def create_consistency_check(
        self,
        source_a_id: str,
        source_b_id: str,
        match_columns: dict[str, str],
        threshold: int,
        position: dict[str, int],
    ) -> dict[str, Any]:
        """Create a consistency check node"""
        node = {
            "id": f"check_consistency_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "consistency",
            "name": "Cross-Table Consistency Check",
            "description": "Checks data consistency between sources",
            "config": {
                "sourceA": source_a_id,
                "sourceB": source_b_id,
                "matchColumns": match_columns,
                "threshold": threshold,
                "rules": [],
            },
            "sourceNodeId": None,  # Multi-source check
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created consistency check: {node['id']}")
        return node

    def create_reconciliation_check(
        self,
        source_a_id: str,
        source_b_id: str,
        match_columns: dict[str, str],
        threshold: int,
        position: dict[str, int],
    ) -> dict[str, Any]:
        """Create a reconciliation check node"""
        node = {
            "id": f"check_reconciliation_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "reconciliation",
            "name": "Data Reconciliation Check",
            "description": "Reconciles data between two sources",
            "config": {
                "sourceA": source_a_id,
                "sourceB": source_b_id,
                "matchColumns": match_columns,
                "comparisonType": "exact_match",
                "threshold": threshold,
                "reportMismatches": True,
            },
            "sourceNodeId": None,  # Multi-source check
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created reconciliation check: {node['id']}")
        return node

    def create_conformity_check(
        self,
        columns: list[str],
        format_spec: str,
        threshold: int,
        source_node_id: str,
        position: dict[str, int],
    ) -> dict[str, Any]:
        """Create a conformity check node"""
        node = {
            "id": f"check_conformity_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "conformity",
            "name": f"Conformity Check - {format_spec}",
            "description": f"Checks if values conform to {format_spec}",
            "config": {"columns": columns, "format": format_spec, "threshold": threshold},
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created conformity check: {node['id']}")
        return node

    def create_accuracy_check(
        self,
        columns: list[str],
        reference_source: str | None,
        threshold: int,
        source_node_id: str,
        position: dict[str, int],
    ) -> dict[str, Any]:
        """Create an accuracy check node"""
        config = {"columns": columns, "threshold": threshold}
        if reference_source:
            config["referenceSource"] = reference_source

        node = {
            "id": f"check_accuracy_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "accuracy",
            "name": "Accuracy Check",
            "description": "Validates data accuracy",
            "config": config,
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created accuracy check: {node['id']}")
        return node

    def create_timeliness_check(
        self,
        date_column: str,
        max_age_days: int,
        threshold: int,
        source_node_id: str,
        position: dict[str, int],
    ) -> dict[str, Any]:
        """Create a timeliness check node"""
        node = {
            "id": f"check_timeliness_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": "timeliness",
            "name": f"Timeliness Check - {date_column}",
            "description": f"Checks if data is up-to-date (max {max_age_days} days old)",
            "config": {
                "dateColumn": date_column,
                "maxAgeDays": max_age_days,
                "threshold": threshold,
            },
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created timeliness check: {node['id']}")
        return node

    def create_generic_check(
        self, check_type: str, config: dict[str, Any], source_node_id: str, position: dict[str, int]
    ) -> dict[str, Any]:
        """Create a generic check node"""
        node = {
            "id": f"check_{check_type}_{uuid4().hex[:8]}",
            "type": "check",
            "checkType": check_type,
            "name": f"{check_type.title()} Check",
            "description": f"Data quality check of type: {check_type}",
            "config": config,
            "sourceNodeId": source_node_id,
            "x": position["x"],
            "y": position["y"],
        }
        logger.debug(f"Created generic check: {node['id']} - {check_type}")
        return node


# Singleton
node_generator = NodeGenerator()
