"""
Complex Flow Builder with LangGraph

Handles multi-step flow building using LangGraph state machine.
"""

import json
import logging
import time
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.llm.utils.cache import flow_builder_cache
from app.services.llm.utils.cost_tracker import cost_tracker
from app.services.llm.utils.node_generator import node_generator
from app.services.llm.utils.retry_logic import RetryConfig, default_retry_handler, retry_on_error
from app.services.llm.utils.validation import flow_validator

logger = logging.getLogger(__name__)


class FlowBuilderState(TypedDict):
    """State schema for LangGraph workflow"""

    # Input (immutable)
    prompt: str
    current_flow: dict[str, Any]
    available_data_sources: list[dict[str, Any]]

    # Parsed data
    parsed_instructions: list[dict[str, Any]]
    data_source_requests: list[dict[str, Any]]
    check_requests: list[dict[str, Any]]

    # Matched/created resources
    matched_sources: list[dict[str, Any]]
    source_nodes: list[dict[str, Any]]
    check_nodes: list[dict[str, Any]]
    connections: list[dict[str, Any]]

    # Error tracking
    errors: list[str]
    warnings: list[str]

    # Metadata
    step_timings: dict[str, float]
    tokens_used: int

    # Output
    final_flow_updates: dict[str, Any] | None
    needs_clarification: bool
    clarification_questions: list[str]
    suggested_data_sources: list[dict[str, Any]] | None
    message: str


class ComplexFlowBuilder:
    """
    Complex flow builder using LangGraph for multi-step processing.

    Workflow Steps:
    1. Parse instructions → Extract atomic operations
    2. Match data sources → Find in current flow or available sources
    3. Generate source nodes → Create new source nodes as needed
    4. Generate check nodes → Create check nodes with configurations
    5. Create connections → Link sources to checks
    6. Validate flow → Ensure valid structure
    7. Handle errors → Convert errors to clarification questions
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.node_generator = node_generator
        self.validator = flow_validator

        # Performance utilities
        self.cache = flow_builder_cache
        self.cost_tracker = cost_tracker
        self.retry_handler = default_retry_handler

        # Retry configuration for LLM calls
        self.retry_config = RetryConfig(
            max_attempts=getattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3),
            initial_delay=getattr(settings, "LLM_RETRY_INITIAL_DELAY", 2.0),
            max_delay=getattr(settings, "LLM_RETRY_MAX_DELAY", 10.0),
        )

        # Build LangGraph workflow
        self.workflow = self._build_workflow()

        logger.info(f"✅ ComplexFlowBuilder initialized - Model: {self.model}")
        logger.info(f"   Cache enabled: {self.cache.enabled}")
        logger.info(f"   Retry attempts: {self.retry_config.max_attempts}")

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph state machine"""
        workflow = StateGraph(FlowBuilderState)

        # Add nodes (steps)
        workflow.add_node("parse_instructions", self._parse_instructions)
        workflow.add_node("match_data_sources", self._match_data_sources)
        workflow.add_node("generate_source_nodes", self._generate_source_nodes)
        workflow.add_node("generate_check_nodes", self._generate_check_nodes)
        workflow.add_node("create_connections", self._create_connections)
        workflow.add_node("validate_flow", self._validate_flow)
        workflow.add_node("handle_errors", self._handle_errors)

        # Define edges (workflow)
        workflow.set_entry_point("parse_instructions")
        workflow.add_edge("parse_instructions", "match_data_sources")
        workflow.add_edge("match_data_sources", "generate_source_nodes")
        workflow.add_edge("generate_source_nodes", "generate_check_nodes")
        workflow.add_edge("generate_check_nodes", "create_connections")
        workflow.add_edge("create_connections", "validate_flow")

        # Conditional routing after validation
        workflow.add_conditional_edges(
            "validate_flow", self._should_handle_errors, {"errors": "handle_errors", "success": END}
        )

        workflow.add_edge("handle_errors", END)

        return workflow.compile()

    async def generate_flow_update(
        self,
        prompt: str,
        current_flow: dict[str, Any],
        available_data_sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Generate flow configuration updates using LangGraph workflow.

        Args:
            prompt: Natural language description
            current_flow: Current flow configuration
            available_data_sources: Available data sources

        Returns:
            Response dict with flow_updates, success status, etc.
        """
        start_time = time.time()
        logger.info("🚀 Complex Flow Builder - Processing request")
        logger.info(f"📝 Prompt: {prompt}")

        # Check cache first
        cached_result = self.cache.get(prompt, current_flow, available_data_sources or [])
        if cached_result:
            logger.info("🎯 Returning cached result")
            return cached_result

        # Initialize state
        initial_state = FlowBuilderState(
            prompt=prompt,
            current_flow=current_flow or {"nodes": [], "connections": []},
            available_data_sources=available_data_sources or [],
            parsed_instructions=[],
            data_source_requests=[],
            check_requests=[],
            matched_sources=[],
            source_nodes=[],
            check_nodes=[],
            connections=[],
            errors=[],
            warnings=[],
            suggested_data_sources=[],
            step_timings={},
            tokens_used=0,
            final_flow_updates=None,
            needs_clarification=False,
            clarification_questions=[],
            message="",
        )

        # Run workflow
        try:
            final_state = await self.workflow.ainvoke(initial_state)

            total_time = time.time() - start_time
            logger.info(f"⏱️ Total processing time: {total_time:.2f}s")

            # Build response
            response = {
                "success": not final_state["needs_clarification"],
                "needs_clarification": final_state["needs_clarification"],
                "clarification_questions": final_state["clarification_questions"],
                "suggested_data_sources": final_state.get("suggested_data_sources"),
                "pending_tasks": final_state.get("check_requests")
                if final_state.get("suggested_data_sources")
                else None,  # Keep tasks in memory
                "flow_updates": final_state["final_flow_updates"],
                "message": final_state["message"],
                "metadata": {
                    "total_time": total_time,
                    "step_timings": final_state["step_timings"],
                    "tokens_used": final_state["tokens_used"],
                    "warnings": final_state["warnings"],
                },
            }

            # Cache successful results
            if response["success"]:
                self.cache.set(prompt, current_flow, available_data_sources or [], response)

            logger.info(f"✅ Complex Flow Builder completed - Success: {response['success']}")
            return response

        except Exception as e:
            logger.error(f"❌ Error in complex flow builder: {type(e).__name__}: {e}")
            logger.exception("Full traceback:")

            return {
                "success": False,
                "needs_clarification": True,
                "clarification_questions": [f"An error occurred: {str(e)}"],
                "flow_updates": None,
                "message": f"Error processing request: {str(e)}",
                "metadata": {"total_time": time.time() - start_time, "error": str(e)},
            }

    # ========================================
    # Helper Methods
    # ========================================

    @retry_on_error()
    async def _call_llm(self, messages: list[dict[str, str]], operation: str, **kwargs) -> Any:
        """
        Call LLM with retry logic and cost tracking.

        Args:
            messages: Chat messages
            operation: Operation name for logging
            **kwargs: Additional arguments for API call

        Returns:
            OpenAI response
        """
        response = await self.client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )

        # Track cost
        if response.usage:
            self.cost_tracker.log_usage(
                model=self.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                operation=operation,
            )

        return response

    # ========================================
    # Workflow Step Implementations
    # ========================================

    async def _parse_instructions(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 1: Parse user prompt into atomic instructions.

        Uses LLM to extract:
        - Data source requests (add/connect/load table)
        - Check requests (completeness, validity, etc.)
        - Dependencies between instructions
        """
        step_start = time.time()
        prompt = state["prompt"]
        current_flow = state["current_flow"]

        # Get existing source names from current flow for context
        existing_sources = []
        for node in current_flow.get("nodes", []):
            if node.get("type") == "source":
                table_name = node.get("config", {}).get("table_name") or node.get("config", {}).get(
                    "tableName"
                )
                if table_name:
                    existing_sources.append(table_name)

        logger.info("📋 Step 1: Parsing instructions...")
        logger.info(
            f"   Existing sources in flow: {existing_sources if existing_sources else 'none'}"
        )

        # Build context for the LLM
        context_info = ""
        if existing_sources:
            context_info = f"\n\nCONTEXT: The current flow already has these data sources: {', '.join(existing_sources)}"
            context_info += (
                "\nIf the user doesn't specify a source for a check, use the first existing source."
            )

        system_prompt = f"""You are an expert at parsing data quality flow instructions.

Extract atomic operations from the user's prompt. For each operation, identify:
1. Type: "add_source" or "add_check"
2. Entity: Table/source name or check type
3. Details: Columns, thresholds, configurations

RESPONSE FORMAT (JSON only):
{{
  "data_source_requests": [
    {{"entity": "customers", "type": "add_source"}}
  ],
  "check_requests": [
    {{
      "type": "completeness",
      "columns": ["email", "name"],
      "threshold": 95,
      "source_dependency": "customers"
    }}
  ]
}}

Rules:
- Infer reasonable defaults (threshold=90 if not specified)
- Extract ALL operations mentioned
- Preserve column names exactly as mentioned
- Identify source dependencies for each check
- If no source is mentioned for a check and existing sources are available, use the first existing source{context_info}
"""

        try:
            response = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this request:\n{prompt}"},
                ],
                operation="parse_instructions",
                temperature=0.1,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            parsed = json.loads(content)

            data_source_requests = parsed.get("data_source_requests", [])
            check_requests = parsed.get("check_requests", [])
            tokens_used = response.usage.total_tokens if response.usage else 0

            logger.info(
                f"✓ Parsed: {len(data_source_requests)} data sources, {len(check_requests)} checks"
            )

            # Log check details for debugging
            for idx, check_req in enumerate(check_requests):
                src_dep = check_req.get("source_dependency")
                check_type = check_req.get("type")
                logger.info(f"   Check {idx + 1}: {check_type} - source_dependency='{src_dep}'")

            step_time = time.time() - step_start

            return {
                "parsed_instructions": data_source_requests + check_requests,
                "data_source_requests": data_source_requests,
                "check_requests": check_requests,
                "tokens_used": tokens_used,
                "step_timings": {"parse_instructions": step_time},
            }

        except Exception as e:
            logger.error(f"❌ Error parsing instructions: {e}")
            return {
                "parsed_instructions": [],
                "data_source_requests": [],
                "check_requests": [],
                "errors": [f"Failed to parse instructions: {str(e)}"],
                "step_timings": {"parse_instructions": time.time() - step_start},
            }

    async def _match_data_sources(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 2: Match requested data sources to existing or available sources.

        Searches in:
        1. Current flow (already added nodes)
        2. Available data sources (from organization)
        3. Fuzzy matching if exact match not found
        """
        step_start = time.time()
        data_source_requests = state["data_source_requests"]
        current_flow = state["current_flow"]
        available_sources = state["available_data_sources"]

        logger.info(f"🔍 Step 2: Matching {len(data_source_requests)} data sources...")

        matched_sources = []
        errors = []
        suggestions = []

        for req in data_source_requests:
            entity = req.get("entity", "").lower()

            # Search in current flow first
            existing = self._find_source_in_flow(entity, current_flow)
            if existing:
                matched_sources.append(
                    {
                        "entity": entity,
                        "source": "current_flow",
                        "node_id": existing["node_id"],
                        "table_name": existing["table_name"],
                        "columns": existing.get("columns", []),
                    }
                )
                logger.info(f"✓ Found '{entity}' in current flow")
                continue

            # Search in available sources
            matched = self._find_in_available_sources(entity, available_sources)
            if matched:
                matched_sources.append(
                    {
                        "entity": entity,
                        "source": "available",
                        "data_source_id": matched["id"],
                        "data_source_name": matched.get("name"),
                        "table_name": matched.get("table_name"),
                        "schema_name": matched.get("schema_name"),
                        "connection_type": matched.get("connection_type"),
                        "columns": matched.get("metadata", {}).get("columns", []),
                        "full_data_source": matched,  # Keep the full object for reference
                    }
                )
                logger.info(f"✓ Matched '{entity}' to available source")
                continue

            # Not found - try fuzzy matching
            fuzzy_matches = self._fuzzy_match_sources(entity, available_sources)
            if fuzzy_matches:
                logger.info(
                    f"⚠️ '{entity}' not found, suggesting {len(fuzzy_matches)} similar sources"
                )
                suggestions.extend(fuzzy_matches)
                errors.append(f"Cannot find data source: '{entity}'")
            else:
                errors.append(f"Cannot find data source: '{entity}'")
                logger.warning(f"⚠️ Data source '{entity}' not found and no similar sources")

        step_time = time.time() - step_start

        return {
            "matched_sources": matched_sources,
            "errors": errors,
            "suggested_data_sources": suggestions,
            "step_timings": {**state["step_timings"], "match_data_sources": step_time},
        }

    def _find_source_in_flow(self, entity: str, flow: dict[str, Any]) -> dict[str, Any] | None:
        """Find data source node in current flow and return in matched_source format"""
        entity_lower = entity.lower()

        for node in flow.get("nodes", []):
            if node.get("type") != "source":
                continue

            name = (node.get("name") or "").lower()
            table_name = (
                node.get("config", {}).get("table_name")
                or node.get("config", {}).get("tableName")
                or ""
            ).lower()

            if entity_lower in name or entity_lower in table_name:
                # Return in the same format as matched_sources
                return {
                    "entity": entity,
                    "node_id": node.get("id"),  # Map id to node_id for consistency
                    "table_name": table_name,
                    "columns": node.get("config", {}).get("metadata", {}).get("columns", []),
                }

        return None

    def _find_in_available_sources(
        self, entity: str, available_sources: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find matching data source from available sources"""
        entity_lower = entity.lower()

        for source in available_sources:
            name = (source.get("name") or "").lower()
            table_name = (source.get("table_name") or "").lower()

            if entity_lower in table_name or entity_lower in name:
                return source

        return None

    def _fuzzy_match_sources(
        self, entity: str, available_sources: list[dict[str, Any]], limit: int = 5
    ) -> list[dict[str, Any]]:
        """Find similar data sources using fuzzy matching"""
        from difflib import SequenceMatcher

        entity_lower = entity.lower()
        matches = []

        for source in available_sources:
            table_name = source.get("table_name") or ""
            name = source.get("name") or ""

            # Calculate similarity score
            table_score = SequenceMatcher(None, entity_lower, table_name.lower()).ratio()
            name_score = SequenceMatcher(None, entity_lower, name.lower()).ratio()
            max_score = max(table_score, name_score) * 100

            # Only include if similarity is above threshold
            if max_score > 30:
                matches.append(
                    {
                        **source,
                        "match_score": round(max_score, 1),
                        "match_reason": f"Similar to '{entity}'",
                    }
                )

        # Sort by match score (highest first) and limit results
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches[:limit]

    async def _generate_source_nodes(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 3: Generate source nodes for matched data sources.

        Only creates nodes for sources not already in current flow.
        """
        step_start = time.time()
        matched_sources = state["matched_sources"]

        logger.info("🏗️ Step 3: Generating source nodes...")

        source_nodes = []

        for idx, matched in enumerate(matched_sources):
            # Skip if already in flow
            if matched.get("source") == "current_flow":
                logger.info(f"⏭️ Skipping '{matched.get('entity')}' - already in flow")
                continue

            # Generate new source node
            node = self.node_generator.create_source_node(
                data_source_id=matched.get("data_source_id"),
                name=matched.get("data_source_name", matched.get("entity")),
                table_name=matched.get("table_name", matched.get("entity")),
                schema_name=matched.get("schema_name"),
                connection_type=matched.get("connection_type"),
                columns=matched.get("columns", []),
                position=self._calculate_source_position(idx),
            )

            # Store node_id in matched_sources for later reference
            matched["node_id"] = node["id"]

            source_nodes.append(node)
            logger.info(f"✓ Created source node '{matched.get('entity')}' (ID: {node['id']})")

        step_time = time.time() - step_start

        return {
            "source_nodes": source_nodes,
            "matched_sources": matched_sources,  # Update with node_ids
            "step_timings": {**state["step_timings"], "generate_source_nodes": step_time},
        }

    def _calculate_source_position(self, index: int) -> dict[str, int]:
        """Calculate position for source node on canvas"""
        return {
            "x": 100,
            "y": 150 + (index * 200),  # Vertical spacing
        }

    async def _generate_check_nodes(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 4: Generate check nodes based on check requests.

        Creates appropriate check configurations for each request type.
        """
        step_start = time.time()
        check_requests = state["check_requests"]
        matched_sources = state["matched_sources"]
        current_flow = state["current_flow"]

        logger.info(f"🔧 Step 4: Generating {len(check_requests)} check nodes...")

        check_nodes = []
        errors = list(state.get("errors", []))
        warnings = list(state.get("warnings", []))

        for idx, check_req in enumerate(check_requests):
            try:
                check_type = check_req.get("type")

                # Find source node for this check
                source_dep = check_req.get("source_dependency")
                source_match = self._find_matched_source(source_dep, matched_sources, current_flow)

                if not source_match:
                    errors.append(
                        f"Cannot create {check_type} check: missing data source '{source_dep}'"
                    )
                    continue

                source_node_id = source_match.get("node_id")

                # Validate columns exist in source
                requested_columns = check_req.get("columns", [])
                available_columns = source_match.get("columns", [])

                if requested_columns and available_columns:
                    # Normalize column names for comparison
                    available_lower = [
                        c.lower() if isinstance(c, str) else str(c).lower()
                        for c in available_columns
                    ]
                    invalid_columns = [
                        col for col in requested_columns if col.lower() not in available_lower
                    ]
                    if invalid_columns:
                        warnings.append(
                            f"Columns not found in {source_dep}: {', '.join(invalid_columns)}"
                        )

                # Generate check node based on type
                position = self._calculate_check_position(idx)

                if check_type == "completeness":
                    node = self.node_generator.create_completeness_check(
                        columns=requested_columns,
                        threshold=check_req.get("threshold", 90),
                        source_node_id=source_node_id,
                        position=position,
                    )

                elif check_type == "validity":
                    node = self.node_generator.create_validity_check(
                        columns=requested_columns,
                        validation_type=check_req.get("validation_type", "custom"),
                        pattern=check_req.get("pattern"),
                        threshold=check_req.get("threshold", 90),
                        source_node_id=source_node_id,
                        position=position,
                    )

                elif check_type == "uniqueness":
                    node = self.node_generator.create_uniqueness_check(
                        columns=requested_columns,
                        threshold=check_req.get("threshold", 100),
                        source_node_id=source_node_id,
                        position=position,
                    )

                elif check_type == "consistency":
                    # Handle cross-table consistency
                    source_b_dep = check_req.get("source_b")
                    source_b_match = self._find_matched_source(
                        source_b_dep, matched_sources, current_flow
                    )

                    if not source_b_match:
                        errors.append(
                            f"Cannot create consistency check: "
                            f"missing second data source '{source_b_dep}'"
                        )
                        continue

                    node = self.node_generator.create_consistency_check(
                        source_a_id=source_node_id,
                        source_b_id=source_b_match.get("node_id"),
                        match_columns=check_req.get("match_columns", {}),
                        threshold=check_req.get("threshold", 100),
                        position=position,
                    )

                elif check_type == "reconciliation":
                    # Similar to consistency but different config
                    source_a_dep = check_req.get("source_a") or source_dep
                    source_b_dep = check_req.get("source_b")

                    source_a_match = self._find_matched_source(
                        source_a_dep, matched_sources, current_flow
                    )
                    source_b_match = self._find_matched_source(
                        source_b_dep, matched_sources, current_flow
                    )

                    if not source_a_match or not source_b_match:
                        errors.append("Cannot create reconciliation check: missing data sources")
                        continue

                    node = self.node_generator.create_reconciliation_check(
                        source_a_id=source_a_match.get("node_id"),
                        source_b_id=source_b_match.get("node_id"),
                        match_columns=check_req.get("match_columns", {}),
                        threshold=check_req.get("threshold", 100),
                        position=position,
                    )

                elif check_type == "conformity":
                    node = self.node_generator.create_conformity_check(
                        columns=requested_columns,
                        format_spec=check_req.get("format", "standard"),
                        threshold=check_req.get("threshold", 90),
                        source_node_id=source_node_id,
                        position=position,
                    )

                elif check_type == "accuracy":
                    node = self.node_generator.create_accuracy_check(
                        columns=requested_columns,
                        reference_source=check_req.get("reference_source"),
                        threshold=check_req.get("threshold", 90),
                        source_node_id=source_node_id,
                        position=position,
                    )

                elif check_type == "timeliness":
                    node = self.node_generator.create_timeliness_check(
                        date_column=check_req.get("date_column", "created_at"),
                        max_age_days=check_req.get("max_age_days", 30),
                        threshold=check_req.get("threshold", 90),
                        source_node_id=source_node_id,
                        position=position,
                    )

                else:
                    # Generic check creation
                    node = self.node_generator.create_generic_check(
                        check_type=check_type,
                        config=check_req,
                        source_node_id=source_node_id,
                        position=position,
                    )

                check_nodes.append(node)
                logger.info(f"✓ Created {check_type} check (ID: {node['id']})")

            except Exception as e:
                logger.error(f"❌ Error creating check node: {e}")
                errors.append(f"Error creating check: {str(e)}")

        step_time = time.time() - step_start

        return {
            "check_nodes": check_nodes,
            "errors": errors,
            "warnings": warnings,
            "step_timings": {**state["step_timings"], "generate_check_nodes": step_time},
        }

    def _find_matched_source(
        self, entity: str, matched_sources: list[dict[str, Any]], current_flow: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Find matched source by entity name"""
        if not entity:
            return None

        entity_lower = entity.lower()

        # Check matched sources
        for source in matched_sources:
            if source.get("entity", "").lower() == entity_lower:
                return source

        # Check current flow
        return self._find_source_in_flow(entity, current_flow)

    def _calculate_check_position(self, index: int) -> dict[str, int]:
        """Calculate position for check node on canvas"""
        return {
            "x": 400,
            "y": 100 + (index * 120),  # Vertical spacing
        }

    async def _create_connections(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 5: Create connections between nodes.

        Links source nodes to check nodes based on dependencies.
        """
        step_start = time.time()
        check_nodes = state["check_nodes"]

        logger.info("🔗 Step 5: Creating connections...")

        connections = []

        for check_node in check_nodes:
            check_type = check_node.get("checkType")

            # Handle multi-source checks (reconciliation, consistency)
            if check_type in ["reconciliation", "consistency"]:
                source_a_id = check_node.get("config", {}).get("sourceA")
                source_b_id = check_node.get("config", {}).get("sourceB")

                if source_a_id:
                    connections.append(
                        {
                            "id": f"conn_{uuid4().hex[:8]}",
                            "from": source_a_id,
                            "to": check_node["id"],
                        }
                    )

                if source_b_id:
                    connections.append(
                        {
                            "id": f"conn_{uuid4().hex[:8]}",
                            "from": source_b_id,
                            "to": check_node["id"],
                        }
                    )

            # Handle single-source checks
            else:
                source_node_id = check_node.get("sourceNodeId")
                if source_node_id:
                    connections.append(
                        {
                            "id": f"conn_{uuid4().hex[:8]}",
                            "from": source_node_id,
                            "to": check_node["id"],
                        }
                    )

        logger.info(f"✓ Created {len(connections)} connections")

        step_time = time.time() - step_start

        return {
            "connections": connections,
            "step_timings": {**state["step_timings"], "create_connections": step_time},
        }

    async def _validate_flow(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 6: Validate complete flow structure.

        Checks:
        - All check nodes have source connections
        - Column names are valid
        - Thresholds are in valid range
        - No circular dependencies
        """
        step_start = time.time()
        source_nodes = state["source_nodes"]
        check_nodes = state["check_nodes"]
        connections = state["connections"]
        errors = list(state.get("errors", []))

        logger.info("✅ Step 6: Validating flow...")

        # Validate using FlowValidator
        validation_result = self.validator.validate_flow_structure(
            source_nodes=source_nodes, check_nodes=check_nodes, connections=connections
        )

        if not validation_result["valid"]:
            errors.extend(validation_result["errors"])

        # Build final output if no errors
        if not errors:
            final_flow_updates = {"nodes": source_nodes + check_nodes, "connections": connections}

            message = self._build_success_message(source_nodes, check_nodes)

            logger.info(
                f"✅ Flow validation passed - "
                f"{len(source_nodes + check_nodes)} nodes, "
                f"{len(connections)} connections"
            )

            step_time = time.time() - step_start

            return {
                "final_flow_updates": final_flow_updates,
                "needs_clarification": False,
                "clarification_questions": [],
                "message": message,
                "step_timings": {**state["step_timings"], "validate_flow": step_time},
            }
        else:
            logger.warning(f"⚠️ Flow validation found {len(errors)} errors")

            step_time = time.time() - step_start

            return {
                "errors": errors,
                "final_flow_updates": None,
                "needs_clarification": True,
                "clarification_questions": errors,
                "message": "Flow validation failed. Please address the errors above.",
                "step_timings": {**state["step_timings"], "validate_flow": step_time},
            }

    def _build_success_message(
        self, source_nodes: list[dict[str, Any]], check_nodes: list[dict[str, Any]]
    ) -> str:
        """Build user-friendly success message"""
        parts = ["✅ Successfully created flow:"]

        if source_nodes:
            source_names = [n.get("name", "Unnamed Source") for n in source_nodes]
            parts.append(f"• Added {len(source_nodes)} data source(s): {', '.join(source_names)}")

        if check_nodes:
            parts.append(f"• Added {len(check_nodes)} quality check(s):")
            for check in check_nodes:
                check_type = check.get("checkType")
                threshold = check.get("config", {}).get("threshold", "N/A")
                parts.append(f"  - {check.get('name')} ({check_type}, {threshold}% threshold)")

        parts.append(f"\nTotal: {len(source_nodes) + len(check_nodes)} nodes, ready to execute!")

        return "\n".join(parts)

    async def _handle_errors(self, state: FlowBuilderState) -> dict[str, Any]:
        """
        Step 7: Handle errors gracefully.

        Converts errors to user-friendly clarification questions.
        Provides partial results if possible.
        Includes data source suggestions if available.
        """
        step_start = time.time()
        errors = state["errors"]
        check_nodes = state.get("check_nodes", [])
        source_nodes = state.get("source_nodes", [])
        suggested_data_sources = state.get("suggested_data_sources", [])

        logger.info(f"⚠️ Step 7: Handling {len(errors)} errors...")

        # Categorize errors
        missing_source_errors = [
            e for e in errors if "Cannot find data source" in e or "missing data source" in e
        ]
        validation_errors = [
            e for e in errors if "validation" in e.lower() or "invalid" in e.lower()
        ]
        other_errors = [
            e for e in errors if e not in missing_source_errors and e not in validation_errors
        ]

        # Build clarification questions
        clarification_questions = []

        if missing_source_errors:
            if suggested_data_sources:
                clarification_questions.append(
                    "⚠️ Data source not found. Did you mean one of these?\n"
                    + "\n".join(
                        f"  • {ds.get('name', ds.get('table_name', 'Unknown'))} ({ds.get('match_score', 0):.0f}% match)"
                        for ds in suggested_data_sources[:3]
                    )
                )
            else:
                clarification_questions.append(
                    "⚠️ Missing Data Sources:\n"
                    + "\n".join(f"  • {e}" for e in missing_source_errors)
                )

        if validation_errors:
            clarification_questions.append(
                "⚠️ Validation Issues:\n" + "\n".join(f"  • {e}" for e in validation_errors)
            )

        if other_errors:
            clarification_questions.extend([f"⚠️ {e}" for e in other_errors])

        # Check if we have partial results
        partial_nodes = source_nodes + check_nodes
        has_partial_results = len(partial_nodes) > 0

        if has_partial_results:
            message = (
                f"⚠️ Partially completed: Created {len(partial_nodes)} nodes, "
                f"but encountered {len(errors)} issue(s). "
                f"Please address the issues above to complete the flow."
            )

            # Include partial results
            final_flow_updates = {
                "nodes": partial_nodes,
                "connections": state.get("connections", []),
            }
        else:
            message = (
                f"❌ Could not create flow due to {len(errors)} error(s). "
                f"Please address the issues above and try again."
            )
            final_flow_updates = None

        step_time = time.time() - step_start

        return {
            "needs_clarification": True,
            "clarification_questions": clarification_questions,
            "suggested_data_sources": suggested_data_sources if suggested_data_sources else None,
            "final_flow_updates": final_flow_updates,
            "message": message,
            "step_timings": {**state["step_timings"], "handle_errors": step_time},
        }

    def _should_handle_errors(self, state: FlowBuilderState) -> str:
        """Conditional routing: Check if errors exist"""
        if state.get("errors"):
            return "errors"
        return "success"
        return "success"


# Singleton instance
complex_flow_builder = ComplexFlowBuilder()
