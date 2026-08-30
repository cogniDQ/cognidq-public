"""
LLM Flow Builder Service

Handles AI-powered flow building through natural language prompts.
Generates flow configurations from user descriptions.
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class FlowBuilderLLM:
    """LLM service for AI-powered flow building"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.temperature = 0.1  # Low temperature for consistent config generation
        self.max_tokens = 2000
        logger.info(f"✅ FlowBuilderLLM initialized - Model: {self.model}")

    async def generate_flow_update(
        self,
        prompt: str,
        current_flow: dict[str, Any],
        available_data_sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Generate flow configuration updates based on user prompt.

        Args:
            prompt: Natural language description of what to add/change
            current_flow: Current flow configuration (nodes, connections)
            available_data_sources: List of available data source nodes from organization

        Returns:
            Dict with:
            - success: bool
            - needs_clarification: bool
            - clarification_questions: List[str] (if needs_clarification)
            - suggested_data_sources: List[Dict] (if requesting data source)
            - flow_updates: Dict (new nodes and connections to add)
            - message: str (explanation of changes)
        """
        logger.info(f"🤖 AI Flow Builder Request - Prompt: '{prompt}'")
        logger.info(
            f"📊 Current flow state - Nodes: {len(current_flow.get('nodes', []))}, Connections: {len(current_flow.get('connections', []))}"
        )
        logger.info(f"🗄️ Available data sources: {len(available_data_sources or [])}")

        # Check if user is requesting a data source
        prompt_lower = prompt.lower()
        data_source_keywords = [
            "add",
            "data source",
            "dataset",
            "table",
            "database",
            "source",
            "connect",
            "employee",
            "customer",
            "order",
            "product",
            "user",
            "transaction",
            "sale",
            "import",
            "load",
            "use",
            "from",
        ]

        # Check if it's a data source request - needs to have action word + potential source reference
        has_action = any(
            word in prompt_lower for word in ["add", "connect", "import", "load", "use"]
        )
        has_source_ref = any(word in prompt_lower for word in data_source_keywords)
        # Or directly mentions a common entity type
        mentions_entity = any(
            word in prompt_lower
            for word in ["employee", "customer", "order", "product", "user", "transaction", "sale"]
        )

        is_data_source_request = (has_action and has_source_ref) or mentions_entity
        logger.info(
            f"🔎 Data source request detection - Action: {has_action}, Source ref: {has_source_ref}, Entity: {mentions_entity}, Is DS request: {is_data_source_request}"
        )

        if is_data_source_request and available_data_sources:
            logger.info("🔍 Detected data source request - searching for matches")
            # Search for matching data sources
            matching_sources = self._find_matching_data_sources(prompt, available_data_sources)

            # If we have matches, return them
            if matching_sources:
                logger.info(f"✅ Found {len(matching_sources)} matching data sources")
                return {
                    "success": False,
                    "needs_clarification": False,
                    "clarification_questions": [],
                    "suggested_data_sources": matching_sources,
                    "flow_updates": None,
                    "message": f"I found {len(matching_sources)} data source(s) that might match your request. Please select one:",
                }

            # If no strong matches but we have available sources, show top 5 anyway
            elif len(available_data_sources) > 0:
                logger.info(
                    f"⚠️ No strong matches, showing all available data sources ({len(available_data_sources)} total)"
                )
                # Add basic score to all sources
                all_sources_with_score = [
                    {**source, "match_score": 10, "match_reason": "Available data source"}
                    for source in available_data_sources[:10]  # Limit to 10
                ]
                return {
                    "success": False,
                    "needs_clarification": False,
                    "clarification_questions": [],
                    "suggested_data_sources": all_sources_with_score,
                    "flow_updates": None,
                    "message": "I couldn't find an exact match. Here are the available data sources - please select one:",
                }

        system_prompt = """You are an expert data quality flow builder AI assistant.

Your task is to help users build data quality flows by understanding their natural language requests and generating proper flow configurations.

AVAILABLE CHECK TYPES:
1. completeness - Checks for null/empty values in specified columns
   Config: {columns: string[], threshold: number (0-100), checkForNull: bool, checkForEmpty: bool}

2. validity - Validates data format/pattern
   Config: {columns: string[], validationType: 'email'|'phone'|'date'|'custom', pattern?: string, threshold: number}

3. uniqueness - Checks for duplicate values
   Config: {columns: string[], threshold: number}

4. conformity - Checks if values conform to expected format/standard
   Config: {columns: string[], format: string, threshold: number}

5. accuracy - Validates data accuracy against reference
   Config: {columns: string[], referenceSource?: string, threshold: number}

6. consistency - Checks data consistency across columns/tables
   Config: {columns: string[], rules: Array<{condition: string}>, threshold: number}

7. timeliness - Checks if data is up-to-date
   Config: {dateColumn: string, maxAgeDays: number, threshold: number}

8. reconciliation - Compares data between sources
   Config: {sourceA: string, sourceB: string, matchColumns: string[], threshold: number}

RULES:
1. Each check node MUST be connected to a data source node (sourceNodeId)
2. Quality threshold is 0-100 (percentage of rows that must pass)
3. Column names must match available columns in the data source
4. If critical information is missing, ask for clarification

RESPONSE FORMAT (JSON only):
{
  "success": true,
  "needs_clarification": false,
  "clarification_questions": [],
  "flow_updates": {
    "nodes": [
      {
        "id": "check_<timestamp>_<random>",
        "type": "check",
        "checkType": "completeness",
        "name": "Email & Age Completeness",
        "config": {
          "columns": ["email", "age"],
          "threshold": 90,
          "checkForNull": true,
          "checkForEmpty": false
        },
        "sourceNodeId": "<source_node_id>",
        "x": 300,
        "y": 150
      }
    ],
    "connections": [
      {
        "id": "conn_<timestamp>_<random>",
        "from": "<source_node_id>",
        "to": "check_<node_id>"
      }
    ]
  },
  "message": "Added completeness check for email and age columns with 90% quality threshold"
}

If information is MISSING:
{
  "success": false,
  "needs_clarification": true,
  "clarification_questions": [
    "Which columns would you like to check?",
    "What quality threshold would you like to use? (0-100)"
  ],
  "flow_updates": null,
  "message": "I need more information to complete this request"
}
"""

        # Build context about current flow
        flow_context = {
            "nodes": current_flow.get("nodes", []),
            "connections": current_flow.get("connections", []),
            "available_data_sources": [],
        }

        # Extract data source nodes for context
        for node in current_flow.get("nodes", []):
            if node.get("type") == "source":
                source_info = {
                    "id": node["id"],
                    "name": node.get("name", "Data Source"),
                    "columns": node.get("config", {}).get("columns", []),
                }
                flow_context["available_data_sources"].append(source_info)

        logger.info(f"📋 Data sources available: {len(flow_context['available_data_sources'])}")
        for ds in flow_context["available_data_sources"]:
            logger.info(
                f"  - {ds['name']} (ID: {ds['id']}, Columns: {len(ds.get('columns', []))}): {ds.get('columns', [])}"
            )

        user_message = f"""Current Flow State:
{json.dumps(flow_context, indent=2)}

User Request: {prompt}

Please generate the flow configuration updates needed to fulfill this request."""

        try:
            logger.info(
                f"🔄 Calling OpenAI API - Model: {self.model}, Temperature: {self.temperature}, Max Tokens: {self.max_tokens}"
            )
            logger.debug(f"📝 User message:\n{user_message}")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )

            logger.info(
                f"✅ OpenAI API response received - Model: {response.model}, Usage: {response.usage}"
            )

            raw_content = response.choices[0].message.content
            logger.info(f"📄 Raw LLM response (first 500 chars): {raw_content[:500]}...")

            result = json.loads(raw_content)
            logger.info(
                f"✨ Parsed result - Success: {result.get('success')}, Needs clarification: {result.get('needs_clarification')}"
            )

            # Validate the response structure
            if not isinstance(result, dict):
                logger.error(f"❌ Invalid response type: {type(result)}")
                raise ValueError("Invalid response format from LLM")

            # Ensure required fields exist
            result.setdefault("success", False)
            result.setdefault("needs_clarification", True)
            result.setdefault("clarification_questions", ["Could you provide more details?"])
            result.setdefault("message", "Unable to process request")

            if result.get("flow_updates"):
                logger.info(
                    f"🔧 Flow updates - Nodes to add: {len(result['flow_updates'].get('nodes', []))}, Connections: {len(result['flow_updates'].get('connections', []))}"
                )

            logger.info("✅ AI Flow Builder completed successfully")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Decode Error: {e}")
            logger.error(
                f"Raw content that failed to parse: {raw_content if 'raw_content' in locals() else 'N/A'}"
            )
            return {
                "success": False,
                "needs_clarification": True,
                "clarification_questions": [
                    "I couldn't understand the request. Could you rephrase it?"
                ],
                "flow_updates": None,
                "message": f"Error parsing response: {str(e)}",
            }
        except Exception as e:
            logger.error(f"❌ Error generating flow update: {type(e).__name__}: {e}")
            logger.exception("Full traceback:")
            return {
                "success": False,
                "needs_clarification": True,
                "clarification_questions": [f"An error occurred: {type(e).__name__}"],
                "flow_updates": None,
                "message": f"Error: {type(e).__name__}processing request",
            }

    def _find_matching_data_sources(
        self, prompt: str, available_sources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Find data sources that match the user's request using fuzzy matching.

        Returns scored and sorted matches.
        """
        logger.info(f"🔍 Searching for data sources matching prompt: '{prompt}'")
        logger.info(f"📊 Analyzing {len(available_sources)} available data sources")

        matches = []
        prompt_lower = prompt.lower()
        prompt_words = set(prompt_lower.split())

        for source in available_sources:
            score = 0
            reasons = []

            # Extract identifiable information
            name = (source.get("name") or "").lower()
            table_name = (source.get("table_name") or "").lower()
            schema_name = (source.get("schema_name") or "").lower()

            # Check column names - HIGHEST PRIORITY (more weight)
            columns = source.get("metadata", {}).get("columns", [])
            if columns:
                # Normalize columns to strings
                column_names = []
                for col in columns:
                    if isinstance(col, str):
                        column_names.append(col.lower())
                    elif isinstance(col, dict):
                        col_name = col.get("column_name") or col.get("name") or ""
                        if col_name:
                            column_names.append(col_name.lower())

                # Check for direct column name matches
                matching_columns = []
                for col in column_names:
                    for word in prompt_words:
                        if word in col or col in word:
                            matching_columns.append(col)

                # Remove duplicates
                matching_columns = list(set(matching_columns))

                if matching_columns:
                    # Give high score for column matches - 25 points per column
                    score += len(matching_columns) * 25
                    reasons.append(f"Columns: {', '.join(matching_columns[:5])}")
                    logger.info(
                        f"  ✓ {table_name or name}: Found {len(matching_columns)} matching columns"
                    )

                # Check for semantic column matches (common patterns)
                column_patterns = {
                    "employee": ["employee", "emp", "staff", "worker", "personnel"],
                    "customer": ["customer", "client", "buyer", "consumer"],
                    "order": ["order", "purchase", "transaction"],
                    "product": ["product", "item", "sku", "merchandise"],
                    "user": ["user", "account", "member"],
                    "email": ["email", "mail", "e_mail"],
                    "phone": ["phone", "telephone", "tel", "mobile"],
                    "address": ["address", "location", "city", "state", "zip"],
                    "date": ["date", "time", "created", "modified", "updated"],
                    "name": ["name", "first_name", "last_name", "full_name"],
                }

                for category, patterns in column_patterns.items():
                    if category in prompt_lower:
                        for col in column_names:
                            if any(pattern in col for pattern in patterns):
                                score += 15
                                reasons.append(f"Has {category}-related columns")
                                break

            # Check table name matches - HIGH PRIORITY
            if table_name:
                if table_name in prompt_lower:
                    score += 40
                    reasons.append("Exact table name match")
                elif any(word in table_name for word in prompt_words if len(word) > 3):
                    score += 20
                    reasons.append("Table name partially matches")

            # Check name matches - MEDIUM PRIORITY
            if name and name != table_name:
                if any(word in name for word in prompt_words):
                    score += 25
                    reasons.append("Name contains keywords")

            # Check schema name - LOW PRIORITY
            if schema_name and schema_name in prompt_lower:
                score += 15
                reasons.append(f"Schema '{schema_name}' matches")

            # Fuzzy keyword matching - LOW PRIORITY
            domain_keywords = [
                "employee",
                "customer",
                "order",
                "product",
                "user",
                "transaction",
                "sale",
                "inventory",
            ]
            for keyword in domain_keywords:
                if keyword in prompt_lower and keyword in (name + table_name):
                    score += 10
                    reasons.append(f"Domain match: {keyword}")

            # Only include sources with some relevance (score > 10)
            if score > 10:
                matches.append(
                    {**source, "match_score": score, "match_reason": " | ".join(reasons)}
                )
                logger.info(
                    f"  📌 {table_name or name}: Score = {score}, Reasons: {' | '.join(reasons)}"
                )

        # Sort by score
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        logger.info(f"✅ Returning top {min(len(matches), 5)} matches out of {len(matches)} total")
        return matches[:5]


# Singleton instance
flow_builder_llm = FlowBuilderLLM()
