"""
Flow Validator Utility

Validates flow structure and configurations.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FlowValidator:
    """Validates flow configurations"""

    def validate_flow_structure(
        self,
        source_nodes: list[dict[str, Any]],
        check_nodes: list[dict[str, Any]],
        connections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Validate complete flow structure.

        Returns:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str]
            }
        """
        errors = []
        warnings = []

        logger.info(
            f"🔍 Validating flow: {len(source_nodes)} sources, {len(check_nodes)} checks, {len(connections)} connections"
        )

        # Validate each check has at least one connection
        check_node_ids = {node["id"] for node in check_nodes}
        connected_checks = {conn["to"] for conn in connections if conn["to"] in check_node_ids}

        unconnected_checks = check_node_ids - connected_checks
        if unconnected_checks:
            # Only error for single-source checks
            for check_id in unconnected_checks:
                check = next((c for c in check_nodes if c["id"] == check_id), None)
                if check and check.get("checkType") not in ["reconciliation", "consistency"]:
                    errors.append(f"Check node '{check_id}' has no source connection")

        # Validate thresholds
        for check in check_nodes:
            threshold = check.get("config", {}).get("threshold")
            if threshold is not None:
                if not isinstance(threshold, (int, float)):
                    errors.append(
                        f"Invalid threshold type in {check['id']}: {type(threshold).__name__} (must be number)"
                    )
                elif not (0 <= threshold <= 100):
                    errors.append(
                        f"Invalid threshold in {check['id']}: {threshold} (must be 0-100)"
                    )

        # Validate column specifications
        for check in check_nodes:
            columns = check.get("config", {}).get("columns", [])
            check_type = check.get("checkType")

            # Skip column validation for multi-source checks
            if check_type in ["reconciliation", "consistency"]:
                continue

            # Timeliness uses dateColumn instead of columns
            if check_type == "timeliness":
                date_column = check.get("config", {}).get("dateColumn")
                if not date_column:
                    warnings.append(f"Check {check['id']} (timeliness) has no dateColumn specified")
                continue

            if not columns:
                warnings.append(f"Check {check['id']} ({check_type}) has no columns specified")

        # Validate no circular dependencies
        if self._has_circular_dependencies(connections):
            errors.append("Circular dependencies detected in flow")

        # Validate source nodes have required fields
        for source in source_nodes:
            config = source.get("config", {})
            # Check for either tableName or table_name
            table_name = config.get("tableName") or config.get("table_name")
            if not table_name:
                errors.append(
                    f"Source node {source['id']} missing tableName or table_name in config"
                )
            if not config.get("columns"):
                warnings.append(f"Source node {source['id']} has no columns")

        is_valid = len(errors) == 0

        if is_valid:
            logger.info("✅ Flow validation passed")
        else:
            logger.warning(f"❌ Flow validation failed with {len(errors)} error(s)")

        if warnings:
            logger.info(f"⚠️ Flow has {len(warnings)} warning(s)")

        return {"valid": is_valid, "errors": errors, "warnings": warnings}

    def _has_circular_dependencies(self, connections: list[dict[str, Any]]) -> bool:
        """Check for circular dependencies using DFS"""
        if not connections:
            return False

        # Build adjacency list
        graph = {}
        for conn in connections:
            from_node = conn["from"]
            to_node = conn["to"]
            if from_node not in graph:
                graph[from_node] = []
            graph[from_node].append(to_node)

        # DFS to detect cycles
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if dfs(node):
                    logger.warning(f"🔄 Circular dependency detected starting from node: {node}")
                    return True

        return False

    def validate_check_config(self, check_type: str, config: dict[str, Any]) -> dict[str, Any]:
        """
        Validate check-specific configuration.

        Returns:
            {
                "valid": bool,
                "errors": List[str]
            }
        """
        errors = []

        # Validate based on check type
        if check_type == "completeness":
            if not config.get("columns"):
                errors.append("Completeness check requires columns")
            if "threshold" not in config:
                errors.append("Completeness check requires threshold")

        elif check_type == "validity":
            if not config.get("columns"):
                errors.append("Validity check requires columns")
            if not config.get("validationType"):
                errors.append("Validity check requires validationType")

        elif check_type == "uniqueness":
            if not config.get("columns"):
                errors.append("Uniqueness check requires columns")

        elif check_type in ["consistency", "reconciliation"]:
            if not config.get("sourceA"):
                errors.append(f"{check_type} check requires sourceA")
            if not config.get("sourceB"):
                errors.append(f"{check_type} check requires sourceB")
            if not config.get("matchColumns"):
                errors.append(f"{check_type} check requires matchColumns")

        elif check_type == "timeliness":
            if not config.get("dateColumn"):
                errors.append("Timeliness check requires dateColumn")
            if "maxAgeDays" not in config:
                errors.append("Timeliness check requires maxAgeDays")

        return {"valid": len(errors) == 0, "errors": errors}


# Singleton
flow_validator = FlowValidator()
