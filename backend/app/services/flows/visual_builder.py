"""
Visual Flow Builder - Helper functions for visual flow builder

This module provides utilities for:
- Auto-layout algorithm for nodes
- Export flow as PNG/SVG
- Import flow from JSON/YAML
- Flow template management
"""

import json
from datetime import datetime
from typing import Any

import yaml

from app.schemas.flow import FlowDefinition, NodePosition


class VisualFlowBuilder:
    """Helper class for visual flow builder operations"""

    def __init__(self):
        """Initialize the visual flow builder"""
        self.default_node_width = 200
        self.default_node_height = 80
        self.horizontal_spacing = 250
        self.vertical_spacing = 150

    def auto_layout(self, flow_definition: FlowDefinition) -> FlowDefinition:
        """
        Automatically layout nodes using a hierarchical layout algorithm

        Args:
            flow_definition: Flow definition to layout

        Returns:
            FlowDefinition with updated node positions
        """
        nodes = flow_definition.nodes
        connections = flow_definition.connections

        if not nodes:
            return flow_definition

        # Build adjacency lists
        children = {node.id: [] for node in nodes}
        parents = {node.id: [] for node in nodes}

        for conn in connections:
            children[conn.source].append(conn.target)
            parents[conn.target].append(conn.source)

        # Find root nodes (nodes with no parents)
        root_nodes = [node.id for node in nodes if not parents[node.id]]

        # If no root nodes, just arrange linearly
        if not root_nodes:
            return self._linear_layout(flow_definition)

        # Assign layers using BFS
        layers: dict[int, list[str]] = {}
        node_layer = {}
        visited = set()

        def assign_layers_bfs(start_nodes: list[str]):
            """BFS to assign nodes to layers"""
            queue = [(node_id, 0) for node_id in start_nodes]

            while queue:
                node_id, layer = queue.pop(0)

                if node_id in visited:
                    continue

                visited.add(node_id)
                node_layer[node_id] = layer

                if layer not in layers:
                    layers[layer] = []
                layers[layer].append(node_id)

                # Add children to queue
                for child_id in children[node_id]:
                    queue.append((child_id, layer + 1))

        assign_layers_bfs(root_nodes)

        # Position nodes
        node_positions = {}

        for layer_idx, node_ids in sorted(layers.items()):
            layer_count = len(node_ids)

            for idx, node_id in enumerate(node_ids):
                # Center nodes vertically within their layer
                y_offset = (idx - (layer_count - 1) / 2) * self.vertical_spacing

                node_positions[node_id] = NodePosition(
                    x=layer_idx * self.horizontal_spacing, y=y_offset
                )

        # Update node positions
        for node in nodes:
            if node.id in node_positions:
                node.position = node_positions[node.id]

        return flow_definition

    def _linear_layout(self, flow_definition: FlowDefinition) -> FlowDefinition:
        """
        Layout nodes in a linear arrangement (fallback)

        Args:
            flow_definition: Flow definition to layout

        Returns:
            FlowDefinition with updated node positions
        """
        for idx, node in enumerate(flow_definition.nodes):
            node.position = NodePosition(x=idx * self.horizontal_spacing, y=0)

        return flow_definition

    def export_to_json(
        self,
        flow_id: str,
        name: str,
        description: str | None,
        flow_definition: dict[str, Any],
        include_metadata: bool = True,
    ) -> str:
        """
        Export flow as JSON

        Args:
            flow_id: Flow UUID
            name: Flow name
            description: Flow description
            flow_definition: Flow definition dict
            include_metadata: Whether to include metadata

        Returns:
            JSON string
        """
        export_data = {"name": name, "description": description, "flow_definition": flow_definition}

        if include_metadata:
            export_data["metadata"] = {
                "flow_id": str(flow_id),
                "exported_at": datetime.utcnow().isoformat(),
                "format_version": "1.0",
            }

        return json.dumps(export_data, indent=2)

    def export_to_yaml(
        self,
        flow_id: str,
        name: str,
        description: str | None,
        flow_definition: dict[str, Any],
        include_metadata: bool = True,
    ) -> str:
        """
        Export flow as YAML

        Args:
            flow_id: Flow UUID
            name: Flow name
            description: Flow description
            flow_definition: Flow definition dict
            include_metadata: Whether to include metadata

        Returns:
            YAML string
        """
        export_data = {"name": name, "description": description, "flow_definition": flow_definition}

        if include_metadata:
            export_data["metadata"] = {
                "flow_id": str(flow_id),
                "exported_at": datetime.utcnow().isoformat(),
                "format_version": "1.0",
            }

        return yaml.dump(export_data, default_flow_style=False, sort_keys=False)

    def import_from_json(self, json_data: str) -> dict[str, Any]:
        """
        Import flow from JSON

        Args:
            json_data: JSON string

        Returns:
            Parsed flow data
        """
        try:
            data = json.loads(json_data)

            # Validate required fields
            if "name" not in data or "flow_definition" not in data:
                raise ValueError("Invalid flow JSON: missing 'name' or 'flow_definition'")

            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}")

    def import_from_yaml(self, yaml_data: str) -> dict[str, Any]:
        """
        Import flow from YAML

        Args:
            yaml_data: YAML string

        Returns:
            Parsed flow data
        """
        try:
            data = yaml.safe_load(yaml_data)

            # Validate required fields
            if "name" not in data or "flow_definition" not in data:
                raise ValueError("Invalid flow YAML: missing 'name' or 'flow_definition'")

            return data
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {str(e)}")

    def create_template_from_flow(
        self, name: str, description: str | None, category: str, flow_definition: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Create a template from a flow

        Args:
            name: Template name
            description: Template description
            category: Template category
            flow_definition: Flow definition

        Returns:
            Template data
        """
        # Strip instance-specific data from template
        template_def = self._sanitize_for_template(flow_definition)

        return {
            "name": name,
            "description": description,
            "category": category,
            "template_definition": template_def,
        }

    def _sanitize_for_template(self, flow_definition: dict[str, Any]) -> dict[str, Any]:
        """
        Remove instance-specific data from flow definition for template

        Args:
            flow_definition: Flow definition to sanitize

        Returns:
            Sanitized flow definition
        """
        # Deep copy to avoid modifying original
        template_def = json.loads(json.dumps(flow_definition))

        # Remove instance-specific IDs from node configs
        if "nodes" in template_def:
            for node in template_def["nodes"]:
                if "config" in node:
                    # Remove data_source_id (user will select their own)
                    if "data_source_id" in node["config"]:
                        node["config"]["data_source_id"] = None

                    # Remove file paths
                    if "file_path" in node["config"]:
                        node["config"]["file_path"] = None

        return template_def

    def get_flow_statistics(self, flow_definition: dict[str, Any]) -> dict[str, Any]:
        """
        Get statistics about a flow

        Args:
            flow_definition: Flow definition

        Returns:
            Statistics dict
        """
        nodes = flow_definition.get("nodes", [])
        connections = flow_definition.get("connections", [])

        # Count node types
        node_type_counts = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1

        # Calculate complexity score (simple heuristic)
        complexity_score = len(nodes) + len(connections) * 0.5

        return {
            "total_nodes": len(nodes),
            "total_connections": len(connections),
            "node_type_counts": node_type_counts,
            "complexity_score": complexity_score,
            "has_source": "source" in node_type_counts,
            "has_checks": "check" in node_type_counts,
            "check_count": node_type_counts.get("check", 0),
        }
