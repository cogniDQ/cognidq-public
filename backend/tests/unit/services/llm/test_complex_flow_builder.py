"""
Unit Tests for ComplexFlowBuilder

Tests the LangGraph workflow and all helper methods.
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.llm.workflows.complex_flow_builder import ComplexFlowBuilder, FlowBuilderState


class TestComplexFlowBuilder:
    """Test suite for ComplexFlowBuilder"""

    def setup_method(self):
        """Setup for each test"""
        self.builder = ComplexFlowBuilder()

    # ========================================
    # Helper Methods Tests
    # ========================================

    def test_find_source_in_flow(self):
        """Test finding source in current flow"""
        current_flow = {
            "nodes": [
                {
                    "id": "source_123",
                    "type": "source",
                    "name": "Customers Table",
                    "config": {"tableName": "customers", "columns": ["id", "name", "email"]},
                }
            ]
        }

        # Test exact match
        result = self.builder._find_source_in_flow("customers", current_flow)
        assert result is not None
        assert result["node_id"] == "source_123"

        # Test partial match
        result = self.builder._find_source_in_flow("cust", current_flow)
        assert result is not None

        # Test not found
        result = self.builder._find_source_in_flow("orders", current_flow)
        assert result is None

    def test_find_in_available_sources(self):
        """Test finding in available data sources"""
        available_sources = [
            {
                "id": "ds_001",
                "name": "Customer Master Data",
                "table_name": "master_data_customers",
                "metadata": {"columns": ["customer_id", "name", "email"]},
            },
            {
                "id": "ds_002",
                "name": "Orders",
                "table_name": "sales_orders",
                "metadata": {"columns": ["order_id", "customer_id"]},
            },
        ]

        # Test match by table name
        result = self.builder._find_in_available_sources("customers", available_sources)
        assert result is not None
        assert result["id"] == "ds_001"

        # Test match by name
        result = self.builder._find_in_available_sources("orders", available_sources)
        assert result is not None
        assert result["id"] == "ds_002"

        # Test not found
        result = self.builder._find_in_available_sources("products", available_sources)
        assert result is None

    def test_calculate_source_position(self):
        """Test source node position calculation"""
        pos0 = self.builder._calculate_source_position(0)
        assert pos0["x"] == 100
        assert pos0["y"] == 150

        pos1 = self.builder._calculate_source_position(1)
        assert pos1["x"] == 100
        assert pos1["y"] == 350  # 150 + (1 * 200)

    def test_calculate_check_position(self):
        """Test check node position calculation"""
        pos0 = self.builder._calculate_check_position(0)
        assert pos0["x"] == 400
        assert pos0["y"] == 100

        pos2 = self.builder._calculate_check_position(2)
        assert pos2["x"] == 400
        assert pos2["y"] == 340  # 100 + (2 * 120)

    def test_find_matched_source(self):
        """Test finding matched source"""
        matched_sources = [
            {
                "entity": "customers",
                "source": "available",
                "node_id": "source_abc",
                "columns": ["id", "name"],
            }
        ]

        current_flow = {"nodes": []}

        result = self.builder._find_matched_source("customers", matched_sources, current_flow)
        assert result is not None
        assert result["entity"] == "customers"
        assert result["node_id"] == "source_abc"

    def test_build_success_message(self):
        """Test success message generation"""
        source_nodes = [{"name": "Customers"}, {"name": "Orders"}]

        check_nodes = [
            {
                "name": "Email Completeness",
                "checkType": "completeness",
                "config": {"threshold": 95},
            },
            {"name": "Email Validity", "checkType": "validity", "config": {"threshold": 98}},
        ]

        message = self.builder._build_success_message(source_nodes, check_nodes)

        assert "Successfully created flow" in message
        assert "2 data source(s)" in message
        assert "Customers" in message
        assert "Orders" in message
        assert "2 quality check(s)" in message
        assert "95% threshold" in message
        assert "98% threshold" in message

    def test_should_handle_errors(self):
        """Test error routing logic"""
        # State with errors
        state_with_errors = FlowBuilderState(
            prompt="test",
            current_flow={},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=["Error 1", "Error 2"],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = self.builder._should_handle_errors(state_with_errors)
        assert result == "errors"

        # State without errors
        state_no_errors = {**state_with_errors, "errors": []}
        result = self.builder._should_handle_errors(state_no_errors)
        assert result == "success"

    # ========================================
    # Integration Tests (Workflow Steps)
    # ========================================

    @pytest.mark.asyncio
    async def test_parse_instructions_simple(self):
        """Test instruction parsing for simple request"""
        import json

        state = FlowBuilderState(
            prompt="Add customers table and check completeness of email column",
            current_flow={},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        # Mock the LLM response so no real API call is made
        llm_content = json.dumps(
            {
                "data_source_requests": [{"entity": "customers", "type": "add_source"}],
                "check_requests": [
                    {
                        "type": "completeness",
                        "columns": ["email"],
                        "threshold": 95,
                        "source_dependency": "customers",
                    }
                ],
            }
        )
        mock_message = MagicMock()
        mock_message.content = llm_content
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.total_tokens = 100
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch.object(self.builder, "_call_llm", new=AsyncMock(return_value=mock_response)):
            result = await self.builder._parse_instructions(state)

        assert "data_source_requests" in result
        assert "check_requests" in result
        assert "tokens_used" in result

        # Should have 1 data source request
        assert len(result["data_source_requests"]) >= 1

        # Should have 1 check request
        assert len(result["check_requests"]) >= 1

    @pytest.mark.asyncio
    async def test_match_data_sources(self):
        """Test data source matching"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[
                {
                    "id": "ds_001",
                    "name": "Customers",
                    "table_name": "customers",
                    "metadata": {"columns": ["id", "name", "email"]},
                }
            ],
            parsed_instructions=[],
            data_source_requests=[{"entity": "customers", "type": "add_source"}],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._match_data_sources(state)

        assert "matched_sources" in result
        assert len(result["matched_sources"]) == 1
        assert result["matched_sources"][0]["entity"] == "customers"
        assert result["matched_sources"][0]["source"] == "available"

    @pytest.mark.asyncio
    async def test_generate_source_nodes(self):
        """Test source node generation"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[
                {
                    "entity": "customers",
                    "source": "available",
                    "data_source_id": "ds_001",
                    "data_source_name": "Customers Table",
                    "table_name": "customers",
                    "columns": ["id", "name", "email"],
                }
            ],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._generate_source_nodes(state)

        assert "source_nodes" in result
        assert len(result["source_nodes"]) == 1

        node = result["source_nodes"][0]
        assert node["type"] == "source"
        assert node["config"]["tableName"] == "customers"
        assert "id" in node

    @pytest.mark.asyncio
    async def test_generate_check_nodes_completeness(self):
        """Test check node generation for completeness"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[
                {
                    "type": "completeness",
                    "columns": ["email", "name"],
                    "threshold": 95,
                    "source_dependency": "customers",
                }
            ],
            matched_sources=[
                {"entity": "customers", "node_id": "source_123", "columns": ["id", "name", "email"]}
            ],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._generate_check_nodes(state)

        assert "check_nodes" in result
        assert len(result["check_nodes"]) == 1

        node = result["check_nodes"][0]
        assert node["type"] == "check"
        assert node["checkType"] == "completeness"
        assert node["config"]["threshold"] == 95
        assert node["config"]["columns"] == ["email", "name"]
        assert node["sourceNodeId"] == "source_123"

    @pytest.mark.asyncio
    async def test_generate_check_nodes_missing_source(self):
        """Test check node generation with missing source"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[
                {
                    "type": "completeness",
                    "columns": ["email"],
                    "threshold": 95,
                    "source_dependency": "nonexistent",
                }
            ],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._generate_check_nodes(state)

        assert "errors" in result
        assert len(result["errors"]) > 0
        assert "missing data source" in result["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_create_connections(self):
        """Test connection creation"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[
                {
                    "id": "check_123",
                    "type": "check",
                    "checkType": "completeness",
                    "sourceNodeId": "source_456",
                }
            ],
            connections=[],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._create_connections(state)

        assert "connections" in result
        assert len(result["connections"]) == 1

        conn = result["connections"][0]
        assert conn["from"] == "source_456"
        assert conn["to"] == "check_123"
        assert "id" in conn

    @pytest.mark.asyncio
    async def test_validate_flow_success(self):
        """Test flow validation - success case"""
        source_node = {
            "id": "source_123",
            "type": "source",
            "config": {"tableName": "customers", "columns": ["id", "email"]},
        }

        check_node = {
            "id": "check_456",
            "type": "check",
            "checkType": "completeness",
            "sourceNodeId": "source_123",
            "config": {"columns": ["email"], "threshold": 90},
        }

        connection = {"id": "conn_789", "from": "source_123", "to": "check_456"}

        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[source_node],
            check_nodes=[check_node],
            connections=[connection],
            errors=[],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._validate_flow(state)

        assert result["needs_clarification"] == False
        assert result["final_flow_updates"] is not None
        assert len(result["final_flow_updates"]["nodes"]) == 2
        assert len(result["final_flow_updates"]["connections"]) == 1
        assert "Successfully created flow" in result["message"]

    @pytest.mark.asyncio
    async def test_validate_flow_with_errors(self):
        """Test flow validation - with errors"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=["Error 1", "Error 2"],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._validate_flow(state)

        assert result["needs_clarification"] == True
        assert len(result["clarification_questions"]) == 2
        assert "validation failed" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_handle_errors_with_partial_results(self):
        """Test error handling with partial results"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[{"id": "source_1"}],
            check_nodes=[{"id": "check_1"}],
            connections=[],
            errors=["Cannot find data source: orders"],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._handle_errors(state)

        assert result["needs_clarification"] == True
        assert len(result["clarification_questions"]) > 0
        assert result["final_flow_updates"] is not None  # Partial results
        assert "Partially completed" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_errors_no_partial_results(self):
        """Test error handling without partial results"""
        state = FlowBuilderState(
            prompt="test",
            current_flow={"nodes": [], "connections": []},
            available_data_sources=[],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=["Critical error"],
            warnings=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        result = await self.builder._handle_errors(state)

        assert result["needs_clarification"] == True
        assert result["final_flow_updates"] is None
        assert "Could not create flow" in result["message"]

    # ========================================
    # End-to-End Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_generate_flow_update_success(self):
        """Test complete workflow - success case"""
        prompt = "Add customers table and check completeness of email with 95% threshold"

        available_sources = [
            {
                "id": "ds_001",
                "name": "Customers",
                "table_name": "customers",
                "metadata": {"columns": ["id", "name", "email", "phone"]},
            }
        ]

        result = await self.builder.generate_flow_update(
            prompt=prompt,
            current_flow={"nodes": [], "connections": []},
            available_data_sources=available_sources,
        )

        assert "success" in result
        assert "flow_updates" in result
        assert "metadata" in result

        # Should have metadata
        assert "total_time" in result["metadata"]
        assert "step_timings" in result["metadata"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
