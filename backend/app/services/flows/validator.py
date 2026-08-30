"""
Flow Validator - Validates flow definitions

This module provides validation logic for flow definitions:
- Structural validation (nodes, connections)
- Circular dependency detection
- Node configuration validation
- Connection compatibility validation
- Orphaned node detection
"""

from collections import defaultdict, deque

from app.schemas.flow import (
    FlowConnection,
    FlowDefinition,
    FlowNode,
    FlowValidationResponse,
    NodeType,
    ValidationError,
)


class FlowValidator:
    """Validator for flow definitions"""

    def __init__(self):
        """Initialize the flow validator"""
        # Define which node types can connect to which
        self.valid_connections = {
            NodeType.SOURCE: [NodeType.CHECK, NodeType.FILTER, NodeType.JOIN, NodeType.TRANSFORM],
            NodeType.CHECK: [NodeType.AGGREGATE],
            NodeType.FILTER: [NodeType.CHECK, NodeType.FILTER, NodeType.TRANSFORM],
            NodeType.JOIN: [NodeType.CHECK, NodeType.FILTER, NodeType.TRANSFORM],
            NodeType.TRANSFORM: [NodeType.CHECK, NodeType.FILTER, NodeType.TRANSFORM],
            NodeType.AGGREGATE: [],  # Terminal node
        }

    def validate_flow(
        self, flow_definition: FlowDefinition, strict: bool = True
    ) -> FlowValidationResponse:
        """
        Validate a complete flow definition

        Args:
            flow_definition: The flow definition to validate
            strict: If False, most errors become warnings (for draft flows)

        Returns:
            FlowValidationResponse with validation results
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        nodes = flow_definition.nodes
        connections = flow_definition.connections

        # Convert nodes to dict for easier lookup
        node_dict = {node.id: node for node in nodes}

        # Allow empty flows (0 nodes)
        if len(nodes) == 0:
            return FlowValidationResponse(
                is_valid=True,
                errors=[],
                warnings=[
                    ValidationError(
                        type="empty_flow", message="Flow is empty - add nodes to make it functional"
                    )
                ],
                node_count=0,
                connection_count=0,
                has_source=False,
                has_checks=False,
                has_circular_dependencies=False,
            )

        # 1. Validate flow has at least one source (warning only)
        source_nodes = [n for n in nodes if n.type == NodeType.SOURCE]
        if not source_nodes:
            warnings.append(
                ValidationError(
                    type="missing_source",
                    message="Flow has no source nodes - add a data source to make it executable",
                )
            )

        # 2. Validate flow has at least one check
        check_nodes = [n for n in nodes if n.type == NodeType.CHECK]
        has_checks = len(check_nodes) > 0
        if not has_checks:
            warnings.append(
                ValidationError(
                    type="no_checks",
                    message="Flow has no check nodes - no data quality validation will be performed",
                )
            )

        # 3. Validate all node references in connections exist
        # For non-strict mode (draft flows), filter out invalid connections
        # instead of failing the entire validation
        invalid_connections = []
        for conn in connections:
            if conn.source not in node_dict:
                invalid_connections.append(conn)
                error = ValidationError(
                    type="invalid_connection",
                    message=f"Connection references non-existent source node: {conn.source}",
                    connection_id=conn.id,
                )
                if strict:
                    errors.append(error)
                else:
                    warnings.append(error)
            elif conn.target not in node_dict:
                invalid_connections.append(conn)
                error = ValidationError(
                    type="invalid_connection",
                    message=f"Connection references non-existent target node: {conn.target}",
                    connection_id=conn.id,
                )
                if strict:
                    errors.append(error)
                else:
                    warnings.append(error)

        # Filter out invalid connections for subsequent validations
        valid_connections = [c for c in connections if c not in invalid_connections]

        # 4. Validate node configurations are complete
        for node in nodes:
            config_errors = self._validate_node_config(node)
            if strict:
                errors.extend(config_errors)
            else:
                # In non-strict mode, treat config errors as warnings
                for error in config_errors:
                    warnings.append(
                        ValidationError(
                            type=error.type,
                            message=error.message + " (configure before executing)",
                            node_id=error.node_id,
                            connection_id=error.connection_id,
                        )
                    )

        # 5. Check for orphaned nodes (nodes with no connections)
        orphaned = self._find_orphaned_nodes(nodes, valid_connections)
        for node_id in orphaned:
            warnings.append(
                ValidationError(
                    type="orphaned_node",
                    message=f"Node '{node_id}' is not connected to any other nodes",
                    node_id=node_id,
                )
            )

        # 6. Check for circular dependencies
        has_circular, cycle_nodes = self._detect_circular_dependencies(nodes, valid_connections)
        if has_circular:
            errors.append(
                ValidationError(
                    type="circular_dependency",
                    message=f"Circular dependency detected involving nodes: {', '.join(cycle_nodes)}",
                )
            )

        # 7. Validate connection compatibility
        compatibility_errors = self._validate_connection_compatibility(nodes, valid_connections)
        if strict:
            errors.extend(compatibility_errors)
        else:
            # In non-strict mode, treat compatibility errors as warnings
            for error in compatibility_errors:
                warnings.append(
                    ValidationError(
                        type=error.type,
                        message=error.message + " (fix before executing)",
                        node_id=error.node_id,
                        connection_id=error.connection_id,
                    )
                )

        # 8. Validate check nodes have source connections
        for check_node in check_nodes:
            has_input = any(conn.target == check_node.id for conn in valid_connections)
            if not has_input:
                if strict:
                    errors.append(
                        ValidationError(
                            type="check_without_source",
                            message=f"Check node '{check_node.id}' has no input connection",
                            node_id=check_node.id,
                        )
                    )
                else:
                    warnings.append(
                        ValidationError(
                            type="check_without_source",
                            message=f"Check node '{check_node.id}' has no input connection (connect before executing)",
                            node_id=check_node.id,
                        )
                    )

        # Build response
        return FlowValidationResponse(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            node_count=len(nodes),
            connection_count=len(valid_connections),
            has_source=len(source_nodes) > 0,
            has_checks=has_checks,
            has_circular_dependencies=has_circular,
        )

    def _validate_node_config(self, node: FlowNode) -> list[ValidationError]:
        """
        Validate node configuration based on node type

        Args:
            node: The node to validate

        Returns:
            List of validation errors
        """
        errors = []

        if node.type == NodeType.SOURCE:
            # Source node must have data_source_id or file reference (file_path or file_id)
            if not node.config:
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Source node '{node.id}' has no configuration",
                        node_id=node.id,
                    )
                )
            elif (
                "data_source_id" not in node.config
                and "dataset_id" not in node.config
                and "file_path" not in node.config
                and "file_id" not in node.config
            ):
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Source node '{node.id}' must specify data_source_id, dataset_id, file_path, or file_id",
                        node_id=node.id,
                    )
                )

        elif node.type == NodeType.CHECK:
            # Check node must have checkType and rule configuration
            if not node.checkType:
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Check node '{node.id}' must specify checkType",
                        node_id=node.id,
                    )
                )
            if not node.config:
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Check node '{node.id}' has no configuration",
                        node_id=node.id,
                    )
                )

        elif node.type == NodeType.JOIN:
            # Join node must specify join type and keys
            if not node.config:
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Join node '{node.id}' has no configuration",
                        node_id=node.id,
                    )
                )
            elif (
                "join_type" not in node.config
                or "left_key" not in node.config
                or "right_key" not in node.config
            ):
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Join node '{node.id}' must specify join_type, left_key, and right_key",
                        node_id=node.id,
                    )
                )

        elif node.type == NodeType.FILTER:
            # Filter node must have filter expression
            if not node.config or "expression" not in node.config:
                errors.append(
                    ValidationError(
                        type="incomplete_config",
                        message=f"Filter node '{node.id}' must specify filter expression",
                        node_id=node.id,
                    )
                )

        return errors

    def _find_orphaned_nodes(
        self, nodes: list[FlowNode], connections: list[FlowConnection]
    ) -> set[str]:
        """
        Find nodes that have no connections

        Args:
            nodes: List of nodes
            connections: List of connections

        Returns:
            Set of orphaned node IDs
        """
        connected_nodes = set()
        for conn in connections:
            connected_nodes.add(conn.source)
            connected_nodes.add(conn.target)

        all_node_ids = {node.id for node in nodes}
        return all_node_ids - connected_nodes

    def _detect_circular_dependencies(
        self, nodes: list[FlowNode], connections: list[FlowConnection]
    ) -> tuple[bool, list[str]]:
        """
        Detect circular dependencies using DFS

        Args:
            nodes: List of nodes
            connections: List of connections

        Returns:
            Tuple of (has_circular_dependency, list_of_nodes_in_cycle)
        """
        # Build adjacency list
        graph = defaultdict(list)
        for conn in connections:
            graph[conn.source].append(conn.target)

        # Track visit states: 0 = unvisited, 1 = visiting, 2 = visited
        visit_state = {node.id: 0 for node in nodes}
        cycle_nodes = []

        def dfs(node_id: str, path: list[str]) -> bool:
            """DFS to detect cycles"""
            if visit_state[node_id] == 1:
                # Found a cycle - extract the cycle nodes
                cycle_start = path.index(node_id)
                cycle_nodes.extend(path[cycle_start:])
                return True

            if visit_state[node_id] == 2:
                return False

            visit_state[node_id] = 1  # Mark as visiting
            path.append(node_id)

            for neighbor in graph[node_id]:
                if dfs(neighbor, path):
                    return True

            path.pop()
            visit_state[node_id] = 2  # Mark as visited
            return False

        # Check all nodes for cycles
        for node in nodes:
            if visit_state[node.id] == 0:
                if dfs(node.id, []):
                    return True, cycle_nodes

        return False, []

    def _validate_connection_compatibility(
        self, nodes: list[FlowNode], connections: list[FlowConnection]
    ) -> list[ValidationError]:
        """
        Validate that connections are between compatible node types

        Args:
            nodes: List of nodes
            connections: List of connections

        Returns:
            List of validation errors
        """
        errors = []
        node_dict = {node.id: node for node in nodes}

        for conn in connections:
            # Skip if nodes don't exist (already caught in earlier validation)
            if conn.source not in node_dict or conn.target not in node_dict:
                continue

            source_node = node_dict[conn.source]
            target_node = node_dict[conn.target]

            # Check if this connection type is allowed
            allowed_targets = self.valid_connections.get(source_node.type, [])
            if target_node.type not in allowed_targets:
                errors.append(
                    ValidationError(
                        type="invalid_connection_type",
                        message=f"Cannot connect {source_node.type.value} node to {target_node.type.value} node",
                        connection_id=conn.id,
                    )
                )

        return errors

    def get_execution_order(
        self, nodes: list[FlowNode], connections: list[FlowConnection]
    ) -> list[str]:
        """
        Calculate execution order using topological sort

        Args:
            nodes: List of nodes
            connections: List of connections

        Returns:
            List of node IDs in execution order
        """
        # Build adjacency list and in-degree count
        graph = defaultdict(list)
        in_degree = {node.id: 0 for node in nodes}

        for conn in connections:
            graph[conn.source].append(conn.target)
            in_degree[conn.target] += 1

        # Find nodes with no incoming edges
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        execution_order = []

        while queue:
            node_id = queue.popleft()
            execution_order.append(node_id)

            # Reduce in-degree for neighbors
            for neighbor in graph[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If not all nodes are in execution_order, there's a cycle
        if len(execution_order) != len(nodes):
            raise ValueError("Cannot create execution order: circular dependency detected")

        return execution_order

    def get_execution_levels(
        self, nodes: list[FlowNode], connections: list[FlowConnection]
    ) -> list[list[str]]:
        """
        Calculate execution levels for parallel execution.
        Nodes at the same level have no dependencies on each other and can run in parallel.

        Args:
            nodes: List of nodes
            connections: List of connections

        Returns:
            List of levels, where each level is a list of node IDs that can execute in parallel
        """
        # Build adjacency list and in-degree count
        graph = defaultdict(list)
        in_degree = {node.id: 0 for node in nodes}

        for conn in connections:
            graph[conn.source].append(conn.target)
            in_degree[conn.target] += 1

        # Process nodes level by level
        execution_levels = []
        current_level = [node_id for node_id, degree in in_degree.items() if degree == 0]

        while current_level:
            # All nodes in current_level can execute in parallel
            execution_levels.append(current_level)

            # Find next level nodes
            next_level = set()
            for node_id in current_level:
                for neighbor in graph[node_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_level.add(neighbor)

            current_level = list(next_level)

        # Verify all nodes are included
        total_nodes = sum(len(level) for level in execution_levels)
        if total_nodes != len(nodes):
            raise ValueError("Cannot create execution levels: circular dependency detected")

        return execution_levels
