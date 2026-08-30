"""
Check Node Handler - Handles data quality check nodes
"""

import logging
import os
import re
from decimal import Decimal
from typing import Any

from app.models.rule import DQRule
from app.schemas.flow import NodeStatus
from app.schemas.rule import ExecutionType
from app.services.execution.result_normalizer import normalize_summary, normalize_violations
from app.services.execution.spark_executor import SparkCheckExecutor
from app.services.flows.node_handlers.base import (
    BaseNodeHandler,
    NodeExecutionContext,
    NodeExecutionResult,
)
from app.services.rules.compiler import RuleCompiler
from app.services.rules.executor import RuleExecutor

logger = logging.getLogger(__name__)


class CheckNodeHandler(BaseNodeHandler):
    """Handler for data quality check nodes"""

    def __init__(self):
        self.rule_executor = RuleExecutor()
        self.rule_compiler = RuleCompiler()
        self.spark_executor = SparkCheckExecutor()

    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        """
        Execute check node - run data quality check

        Args:
            context: Node execution context

        Returns:
            NodeExecutionResult with check results
        """
        try:
            config = context.node_config
            input_data = context.input_data

            # Unwrap checkConfig wrapper from new panel format
            # Frontend saves: { checkConfig: { subtype, columns, ... }, canonicalRule: {...} }
            # Backend expects flat config with type-specific keys
            if isinstance(config, dict) and "checkConfig" in config:
                config = {**config.get("checkConfig", {})}

            # Map frontend 'subtype' to backend type-specific keys
            subtype = config.get("subtype")
            if subtype:
                check_type_key = context.check_type or config.get("checkType")
                SUBTYPE_KEY_MAP = {
                    "completeness": "checkMode",
                    "validity": "validationType",
                    "uniqueness": "uniquenessMode",
                    "conformity": "conformityType",
                    "consistency": "consistencyType",
                    "timeliness": "timelinessType",
                    "accuracy": "accuracyType",
                    "reconciliation": "reconciliationType",
                }
                mapped_key = SUBTYPE_KEY_MAP.get(check_type_key)
                if mapped_key and mapped_key not in config:
                    config[mapped_key] = subtype

            # Debug logging
            logger.info(f"\n{'=' * 60}")
            logger.info("🔍 CHECK NODE EXECUTION START")
            logger.info(f"   Node ID: {context.node_id}")
            logger.info(f"   Check Type: {context.check_type}")
            logger.info(f"   Config Received: {config}")
            logger.info(f"   Input Data Keys: {list(input_data.keys())}")
            logger.info(f"   Full Input Data: {input_data}")  # Log full input data
            if "columns" in input_data:
                logger.info(f"   Input Columns from Source: {input_data.get('columns', [])}")
            if "data_source" in input_data:
                ds = input_data.get("data_source", {})
                logger.info(
                    f"   Input Data Source: {ds.get('name', 'Unknown')} (type: {ds.get('type', 'Unknown')})"
                )
                logger.info(f"   Full Data Source: {ds}")
            logger.info(f"{'=' * 60}")

            # Get check type from context (passed from node.checkType)
            check_type = context.check_type or config.get("checkType")
            if not check_type:
                logger.error("❌ No checkType specified in check node configuration")
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message="No checkType specified in check node configuration",
                )

            # Get source data from input
            if "data_source" not in input_data:
                logger.error(
                    "❌ Check node requires input from a source node - data_source missing"
                )
                logger.error(f"   Available input keys: {list(input_data.keys())}")
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message="Check node requires input from a source node",
                )

            data_source = input_data["data_source"]
            schema_name = input_data.get("schema_name", "default")
            table_name = input_data.get("table_name", "data")
            is_file_source = (
                input_data.get("is_file_source", False) or data_source.get("type") == "file"
            )

            logger.info("📋 Source Information:")
            logger.info(f"   Schema: {schema_name}, Table: {table_name}")
            logger.info(f"   Is File Source: {is_file_source}")
            logger.info(f"   Data Source Type: {data_source.get('type', 'Unknown')}")

            # For file sources, reload the full file data (we only store sample in DB)
            dataframe = None
            if is_file_source:
                file_path = data_source.get("file_path")
                file_type = data_source.get("file_type", "csv")
                logger.info("📄 File source detected - need to reload file data")
                logger.info(f"   File path: {file_path}")
                logger.info(f"   File type: {file_type}")

                if file_path:
                    try:
                        from app.services.ingestion.file_upload import FileUploadService

                        # Use FileUploadService to handle both MinIO and local files
                        file_service = FileUploadService()

                        logger.info(f"📂 Parsing file: {file_path}")
                        # Parse the file (handles MinIO URLs and local paths)
                        parse_result = file_service.parse_file(
                            file_path=file_path,
                            file_type=file_type,
                            original_filename=data_source.get("name", "data"),
                        )

                        dataframe = parse_result.data
                        logger.info(
                            f"✅ File reloaded successfully - DataFrame shape: {dataframe.shape}"
                        )
                        logger.info(f"   Columns: {list(dataframe.columns)}")
                        logger.info(f"   Row count: {len(dataframe)}")
                        logger.info(f"   First few rows:\n{dataframe.head(2)}")
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to reload file {file_path}: {type(e).__name__}: {str(e)}"
                        )
                        logger.error("Exception details:", exc_info=True)
                        return NodeExecutionResult(
                            status=NodeStatus.FAILED,
                            error_message=f"Failed to reload file data: {str(e)}",
                        )
                else:
                    logger.error("⚠️ File source detected but no file_path provided in data_source!")
                    logger.error(f"   Data source content: {data_source}")
                    return NodeExecutionResult(
                        status=NodeStatus.FAILED, error_message="File source missing file_path"
                    )

            logger.info(f"Source type: {'FILE' if is_file_source else 'DATABASE'}")
            if is_file_source:
                logger.info(
                    f"File source detected - DataFrame shape: {dataframe.shape if dataframe is not None else 'None'}"
                )

            # Check if there's an existing rule, or create adhoc rule
            rule_id = config.get("rule_id")
            canonical_rule = None  # Initialize to avoid UnboundLocalError
            execution_mode = "unknown"  # Initialize to avoid UnboundLocalError

            logger.info("📑 Rule Configuration:")
            logger.info(f"   Rule ID: {rule_id or 'None (creating adhoc rule)'}")

            if rule_id:
                logger.info(f"🔎 Looking up existing rule: {rule_id}")
                # Use existing rule
                rule = (
                    context.db.query(DQRule)
                    .filter(DQRule.id == rule_id, DQRule.workspace_id == context.workspace_id)
                    .first()
                )

                if not rule:
                    logger.error(f"❌ Rule {rule_id} not found in database")
                    return NodeExecutionResult(
                        status=NodeStatus.FAILED, error_message=f"Rule {rule_id} not found"
                    )

                logger.info(f"✅ Rule found: {rule.name}")
                # Execute the rule
                logger.info("▶️ Executing predefined rule...")
                if rule.data_source:
                    execution_result = await self.rule_executor.execute_rule(
                        db=context.db,
                        rule=rule,
                        execution_type=ExecutionType.TRIGGERED,
                        sample_only=context.execution_config.get("sample_only", False),
                    )
                    logger.info("✅ Rule execution completed")
                    # Convert RuleExecution ORM object to dict for uniform downstream processing
                    if hasattr(execution_result, "rows_scanned"):
                        violations = []
                        if execution_result.result_details and isinstance(
                            execution_result.result_details, dict
                        ):
                            violations = execution_result.result_details.get("violations", [])
                        execution_result = {
                            "rows_scanned": execution_result.rows_scanned or 0,
                            "rows_passed": execution_result.rows_passed or 0,
                            "rows_failed": execution_result.rows_failed or 0,
                            "pass_rate": float(execution_result.pass_rate or 0),
                            "error": execution_result.error_message,
                            "violations": violations,
                            "status": execution_result.status,
                        }
                    execution_mode = "rule_based"
                else:
                    # Rule has no data_source_id — fall back to adhoc execution
                    # using the source node's connection from input_data.
                    logger.warning(
                        f"⚠️ Rule {rule_id} has no data_source configured — "
                        f"falling back to source-node connection for execution"
                    )
                    canonical_rule = rule.canonical_rule or {}

                    # Build compiled SQL dict from the rule's already-compiled SQL
                    # Keys MUST match what _execute_adhoc_check looks for:
                    # compiled_postgres / compiled_mysql / compiled_snowflake / compiled_sql
                    compiled_sql_dict: dict = {}
                    if getattr(rule, "compiled_postgres", None):
                        compiled_sql_dict["compiled_postgres"] = rule.compiled_postgres
                    if getattr(rule, "compiled_mysql", None):
                        compiled_sql_dict["compiled_mysql"] = rule.compiled_mysql
                    if getattr(rule, "compiled_snowflake", None):
                        compiled_sql_dict["compiled_snowflake"] = rule.compiled_snowflake
                    if getattr(rule, "compiled_sql", None):
                        compiled_sql_dict["compiled_sql"] = rule.compiled_sql
                    if not compiled_sql_dict:
                        # Nothing stored yet — compile now from canonical rule
                        logger.info("🔨 No compiled SQL on rule — compiling from canonical rule...")
                        compiled_sql_dict = self.rule_compiler.compile_rule(
                            canonical_rule,
                            target_schema=rule.target_schema or schema_name,
                            target_table=rule.target_table or table_name,
                        )

                    logger.info("▶️ Executing rule SQL via source-node connection (adhoc path)...")
                    execution_result = await self._execute_adhoc_check(
                        context, data_source, compiled_sql_dict, canonical_rule
                    )
                    logger.info(f"✅ Fallback adhoc execution result: {execution_result}")
                    execution_mode = "rule_based_fallback"

            else:
                # Create adhoc rule from node config
                logger.info("🔧 Creating adhoc rule from node config")

                # ⚠️ VALIDATE: Check if configured columns exist in source
                configured_columns = config.get("columns", [])
                source_columns = input_data.get("columns", [])

                logger.info("📊 Column Validation:")
                logger.info(f"   Configured columns: {configured_columns}")
                logger.info(f"   Source columns: {source_columns}")

                if configured_columns and source_columns:
                    # Extract column names from source (might be dicts)
                    if source_columns and isinstance(source_columns[0], dict):
                        source_col_names = set(
                            col.get("name") for col in source_columns if col.get("name")
                        )
                    else:
                        source_col_names = set(source_columns)

                    # Check for mismatches
                    invalid_columns = [
                        col for col in configured_columns if col not in source_col_names
                    ]

                    if invalid_columns:
                        # Check if ALL columns are invalid (likely changed dataset)
                        all_invalid = len(invalid_columns) == len(configured_columns)
                        valid_columns = [
                            col for col in configured_columns if col in source_col_names
                        ]

                        logger.error("❌ COLUMN MISMATCH DETECTED!")
                        logger.error(f"   Configured columns: {configured_columns}")
                        logger.error(f"   Source columns: {list(source_col_names)}")
                        logger.error(f"   Invalid columns: {invalid_columns}")
                        logger.error(f"   Valid columns: {valid_columns}")

                        if all_invalid:
                            # All columns are invalid - likely the dataset was changed
                            error_msg = (
                                f"❌ DATASET CHANGE DETECTED\n\n"
                                f"None of the configured columns exist in the current source dataset. "
                                f"This usually happens when you change the source data from one table/file to another.\n\n"
                                f"📋 Current source has these columns:\n   {', '.join(list(source_col_names)[:15])}\n\n"
                                f"⚙️ Configured check expects these columns:\n   {', '.join(configured_columns)}\n\n"
                                f"🔧 TO FIX THIS:\n"
                                f"   1. Open this check node's settings\n"
                                f"   2. Remove the old columns: {', '.join(configured_columns[:5])}{'...' if len(configured_columns) > 5 else ''}\n"
                                f"   3. Select new columns from the current dataset\n"
                                f"   4. Save and re-execute the flow\n\n"
                                f"💡 TIP: After changing a source dataset, always reconfigure downstream check nodes!"
                            )
                        else:
                            # Only some columns are invalid - partial configuration error
                            error_msg = (
                                f"❌ COLUMN CONFIGURATION ERROR\n\n"
                                f"{len(invalid_columns)} of {len(configured_columns)} configured column(s) do not exist in the source.\n\n"
                                f"❌ Invalid columns ({len(invalid_columns)}):\n   {', '.join(invalid_columns)}\n\n"
                                f"✅ Valid columns ({len(valid_columns)}):\n   {', '.join(valid_columns) if valid_columns else 'None'}\n\n"
                                f"📋 Available source columns:\n   {', '.join(list(source_col_names)[:15])}\n\n"
                                f"🔧 TO FIX THIS:\n"
                                f"   1. Open this check node's settings\n"
                                f"   2. Remove invalid columns: {', '.join(invalid_columns)}\n"
                                f"   3. Keep or adjust valid columns: {', '.join(valid_columns) if valid_columns else 'N/A'}\n"
                                f"   4. Save and re-execute the flow"
                            )

                        return NodeExecutionResult(
                            status=NodeStatus.FAILED, error_message=error_msg
                        )
                    else:
                        logger.info("✅ All configured columns exist in source")

                logger.info("🔨 Building canonical rule...")

                # Pre-resolve reference_dataset UUID → schema.table before building rule
                _UUID_RE = re.compile(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
                )
                _ref_ds_raw = config.get("reference_dataset") or config.get("referenceDataset")
                if _ref_ds_raw and _UUID_RE.match(str(_ref_ds_raw)):
                    try:
                        from sqlalchemy import text as _text

                        _row = context.db.execute(
                            _text(
                                "SELECT schema_name, physical_identifier "
                                "FROM control.datasets "
                                "WHERE dataset_id = CAST(:id AS UUID)"
                            ),
                            {"id": str(_ref_ds_raw)},
                        ).fetchone()
                        if _row:
                            _schema_r, _phys_r = _row[0], _row[1]
                            _resolved = f"{_schema_r}.{_phys_r}" if _schema_r else _phys_r
                            config = {**config, "reference_dataset": _resolved}
                            logger.info(
                                f"✅ Resolved reference dataset UUID {_ref_ds_raw} → {_resolved}"
                            )
                        else:
                            logger.warning(
                                "reference_lookup: dataset UUID %s not found in DB", _ref_ds_raw
                            )
                    except Exception as _e:
                        logger.warning(
                            "reference_lookup: failed to resolve dataset UUID %s: %s",
                            _ref_ds_raw,
                            _e,
                        )

                canonical_rule = self._build_canonical_rule(
                    check_type, config, schema_name, table_name
                )

                logger.info(f"✅ Canonical rule created: {canonical_rule}")

                # For file sources, ALWAYS use Spark with DataFrame
                # For database sources, determine execution mode
                if is_file_source:
                    logger.info("📄 File source detected - using Spark with DataFrame")
                    execution_mode = "spark"  # File sources always use Spark

                    # Ensure we have a DataFrame
                    if dataframe is None:
                        logger.error("❌ File source provided but no DataFrame found")
                        return NodeExecutionResult(
                            status=NodeStatus.FAILED,
                            error_message="File source provided but no DataFrame found",
                        )

                    logger.info("⚡ Compiling rule for Spark execution...")
                    # Compile for Spark - for file sources, don't use schema prefix
                    # Temporary views are created without schema qualification
                    compiled_sql = self.rule_compiler.compile_rule_for_spark(
                        canonical_rule=canonical_rule,
                        target_schema=None,  # No schema for file sources (temp views)
                        target_table=table_name,
                    )
                    logger.info(
                        f"✅ Spark SQL compiled: {compiled_sql[:200] if compiled_sql else 'None'}..."
                    )

                    # Sprint 4.3 — also compile the per-row violation_sql so the Spark
                    # executor can return sample failing rows for file connectors,
                    # matching the DB-backed path behaviour.
                    violation_sql_for_spark = None
                    try:
                        compiled_dict = self.rule_compiler.compile_rule(
                            canonical_rule=canonical_rule,
                            target_schema=None,
                            target_table=table_name,
                        )
                        raw_vsql = (
                            compiled_dict.get("violation_sql")
                            if isinstance(compiled_dict, dict)
                            else None
                        )
                        if raw_vsql:
                            violation_sql_for_spark = self.rule_compiler._adjust_for_spark_sql(
                                raw_vsql
                            )
                    except Exception as _ve:  # noqa: BLE001
                        logger.warning("Failed to compile violation_sql for file source: %s", _ve)

                    # Execute with DataFrame
                    logger.info("▶️ Executing check on DataFrame via Spark...")
                    logger.info("   DataFrame to execute:")
                    logger.info(f"     Shape: {dataframe.shape}")
                    logger.info(f"     Columns: {list(dataframe.columns)}")
                    logger.info(f"     Row count: {len(dataframe)}")
                    logger.info(
                        f"     Memory usage: {dataframe.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB"
                    )

                    execution_result = await self.spark_executor.execute_check_on_dataframe(
                        dataframe=dataframe,
                        table_name=table_name,
                        compiled_sql=compiled_sql,
                        canonical_rule=canonical_rule,
                        violation_sql=violation_sql_for_spark,
                    )
                    logger.info("✅ Spark execution completed")
                    logger.info(f"   Result: {execution_result}")
                else:
                    # Database source - determine execution mode (direct vs Spark)
                    logger.info("📊 Database source - determining execution mode...")
                    execution_mode = await self._determine_execution_mode(
                        data_source, schema_name, table_name, config
                    )

                    logger.info(f"✅ Selected execution mode: {execution_mode}")

                    if execution_mode == "spark":
                        logger.info("⚡ Using Spark execution for database source")
                        # Compile for Spark and execute via Spark
                        compiled_sql = self.rule_compiler.compile_rule_for_spark(
                            canonical_rule=canonical_rule,
                            target_schema=schema_name,
                            target_table=table_name,
                        )
                        logger.info(f"   Spark SQL: {compiled_sql[:200]}...")

                        logger.info("▶️ Executing check via Spark...")
                        execution_result = await self.spark_executor.execute_check(
                            data_source_config=data_source,
                            compiled_sql=compiled_sql,
                            canonical_rule=canonical_rule,
                            sample_only=context.execution_config.get("sample_only", False),
                        )
                        logger.info(f"✅ Spark execution result: {execution_result}")
                    else:
                        logger.info("🔗 Using direct execution for database source")
                        # Compile rule to SQL (direct execution)
                        logger.info("🔨 Compiling rule to SQL...")
                        compiled_sql_dict = self.rule_compiler.compile_rule(
                            canonical_rule=canonical_rule,
                            target_schema=schema_name,
                            target_table=table_name,
                        )
                        logger.info(f"✅ SQL compiled: {list(compiled_sql_dict.keys())}")

                        # Detect compilation errors early (compiler returns error dict on bad config)
                        if compiled_sql_dict.get("error"):
                            err_msg = (
                                compiled_sql_dict.get("error_message")
                                or compiled_sql_dict.get("error_detail")
                                or compiled_sql_dict.get("error")
                            )
                            logger.error(
                                "Rule compilation error. canonical=%s schema=%s table=%s "
                                "compiled=%s",
                                canonical_rule,
                                schema_name,
                                table_name,
                                compiled_sql_dict,
                            )
                            raise ValueError(f"Rule compilation failed: {err_msg}")

                        # Execute adhoc check via direct connector
                        logger.info("▶️ Executing adhoc check via direct connector...")
                        execution_result = await self._execute_adhoc_check(
                            context, data_source, compiled_sql_dict, canonical_rule
                        )
                        logger.info(f"✅ Direct execution result: {execution_result}")

            # Extract checked columns from config or canonical rule
            checked_columns = config.get("columns", [])
            if not checked_columns and canonical_rule:
                # Extract from canonical rule entity (e.g., "table.column")
                entity = canonical_rule.get("entity", "")
                if "." in entity:
                    column = entity.split(".", 1)[1]
                    checked_columns = [column]

            # If still no columns but we have columns from source input_data, use those
            if not checked_columns and "columns" in input_data:
                logger.warning(
                    "⚠️ Check node has no columns configured, inferring from source columns"
                )
                source_columns = input_data.get("columns", [])
                # Extract column names if they're dicts
                if source_columns and isinstance(source_columns[0], dict):
                    checked_columns = [col.get("name") for col in source_columns if col.get("name")]
                else:
                    checked_columns = source_columns

            logger.info("📊 Processing execution results...")
            logger.info(f"   Checked columns: {checked_columns}")
            logger.info(f"   Execution result keys: {list(execution_result.keys())}")

            # Check for errors in execution result
            if "error" in execution_result and execution_result.get("error"):
                logger.error("❌ EXECUTION ERROR DETECTED:")
                logger.error(f"   Error: {execution_result.get('error')}")
                logger.error(f"   Full execution_result: {execution_result}")
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message=f"Check execution failed: {execution_result.get('error')}",
                )

            # Get column name (single column for most checks)
            column_name = (
                checked_columns[0] if checked_columns and len(checked_columns) == 1 else None
            )

            # Get thresholds from config (accept both naming conventions)
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold")
            )
            threshold_warn = config.get("threshold_warn") or config.get("thresholdWarn")
            threshold_str = f"{threshold}%" if threshold else None

            # Calculate actual and expected values
            rows_scanned = execution_result.get("rows_scanned", 0)
            rows_passed = execution_result.get("rows_passed", 0)
            rows_failed = execution_result.get("rows_failed", 0)
            pass_rate = float(execution_result.get("pass_rate", 0))

            # Determine check status using threshold logic
            threshold_pass_val = float(threshold) if threshold else 100.0
            threshold_warn_val = float(threshold_warn) if threshold_warn is not None else None
            check_status = self._determine_check_status(
                pass_rate, threshold_pass_val, threshold_warn_val
            )

            # Build node label: prefer ruleName, fall back to check_type + subtype
            rule_name = config.get("ruleName") or config.get("rule_name", "")
            subtype_label = config.get("subtype", "")
            if rule_name:
                node_label = rule_name
            elif subtype_label:
                node_label = f"{check_type} / {subtype_label}"
            else:
                node_label = check_type

            # Build enhanced result_data following NODE_RESULT_DATA_STRUCTURE.md
            # For file sources, use original file name for display; for DB sources use schema.table
            if is_file_source:
                dataset_display = data_source.get("name", table_name)  # Use original file name
            else:
                dataset_display = f"{schema_name}.{table_name}"

            result_data = {
                "check_type": check_type,
                "node_label": node_label,
                "dataset": dataset_display,
                "column": column_name,
                "threshold": threshold_str,
                "threshold_pass": threshold_pass_val,
                "threshold_warn": threshold_warn_val,
                "check_status": check_status,
                "rows_scanned": rows_scanned,
                "rows_passed": rows_passed,
                "rows_failed": rows_failed,
                "pass_rate": pass_rate,
                "actual_value": pass_rate,  # For consistency with report expectations
                "expected_value": threshold_pass_val,
                "violations": execution_result.get("violations", [])[:100],  # Limit to 100 samples
                "columns": checked_columns,  # ✅ FIX: Use checked columns, not all table columns
            }

            # For group completeness: surface per-group breakdown in result_data
            if execution_result.get("check_mode") == "group":
                result_data["check_mode"] = "group"
                result_data["group_results"] = execution_result.get("metadata", {}).get(
                    "group_results", []
                )

            # Log what columns we're using
            logger.info(f"✅ Check node columns set to: {checked_columns}")

            # Keep legacy fields for backward compatibility
            result_data.update(
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "execution_engine": execution_mode,
                    "checked_columns": checked_columns,
                    "violation_count": len(execution_result.get("violations", [])),
                }
            )

            # F092: Canonical DQ Output Model — normalize results
            try:
                _exec_ctx = {
                    "execution_id": str(context.execution_id)
                    if context and hasattr(context, "execution_id") and context.execution_id
                    else None,
                    "execution_timestamp": None,
                    "execution_duration_ms": None,
                }
                if canonical_rule:
                    result_data["canonical_summary"] = normalize_summary(
                        execution_result, canonical_rule, _exec_ctx
                    )
                    result_data["canonical_violations"] = normalize_violations(
                        execution_result.get("violations", [])[:100],
                        canonical_rule,
                        _exec_ctx,
                    )
                else:
                    result_data["canonical_summary"] = {}
                    result_data["canonical_violations"] = []
            except Exception as _norm_err:
                logger.warning(f"Canonical normalization failed: {_norm_err}")
                result_data["canonical_summary"] = {}
                result_data["canonical_violations"] = []

            # Determine node status based on check_status (PASS/WARN/FAIL)
            if check_status == "PASS":
                node_status = NodeStatus.COMPLETED
            elif check_status == "WARN":
                node_status = NodeStatus.WARNING
            else:
                node_status = NodeStatus.FAILED

            logger.info("🏁 Check execution complete:")
            logger.info(f"   Rows scanned: {rows_scanned}")
            logger.info(f"   Rows passed: {rows_passed}")
            logger.info(f"   Rows failed: {rows_failed}")
            logger.info(f"   Pass rate: {pass_rate}%")
            logger.info(f"   Threshold pass: {threshold_pass_val}%")
            logger.info(
                f"   Threshold warn: {threshold_warn_val}%"
                if threshold_warn_val is not None
                else "   Threshold warn: N/A"
            )
            logger.info(f"   Check status: {check_status}")
            logger.info(f"   Node status: {node_status}")

            # Output data for downstream nodes
            output_data = {
                **input_data,  # Pass through input data
                "check_result": result_data,
                "passed": check_status in ("PASS", "WARN"),
            }

            logger.info(f"✅ CHECK NODE EXECUTION COMPLETE - status: {node_status}")
            logger.info(f"{'=' * 60}\n")

            return NodeExecutionResult(
                status=node_status, result_data=result_data, output_data=output_data
            )

        except Exception as e:
            logger.error(f"❌ CHECK NODE EXCEPTION: {type(e).__name__}: {str(e)}")
            logger.error("Exception details:", exc_info=True)
            return self.handle_error(e, context)

    def validate_config(self, config: dict[str, Any]) -> bool:
        """
        Validate check node configuration

        Args:
            config: Node configuration

        Returns:
            True if valid
        """
        # Must have checkType
        if "checkType" not in config:
            return False

        # If rule_id not provided, must have check-specific config
        if "rule_id" not in config:
            check_type = config.get("checkType")

            # Validate type-specific config
            if check_type == "completeness":
                return "columns" in config
            elif check_type == "validity":
                return "columns" in config and "rule" in config
            elif check_type == "uniqueness":
                return "columns" in config
            # Add more validations for other check types

        return True

    async def _determine_execution_mode(
        self, data_source: dict[str, Any], schema_name: str, table_name: str, config: dict[str, Any]
    ) -> str:
        """
        Determine whether to use Spark or direct execution.

        Args:
            data_source: Data source configuration
            schema_name: Schema name
            table_name: Table name
            config: Node configuration

        Returns:
            'spark' or 'direct'
        """
        # Get thresholds from environment
        auto_threshold = int(os.getenv("SPARK_AUTO_THRESHOLD", "50000"))
        force_threshold = int(os.getenv("SPARK_FORCE_THRESHOLD", "500000"))

        # Check user preference from config
        user_preference = config.get("execution_mode")  # 'spark', 'direct', or None

        # If user explicitly chose a mode, respect it (unless dataset is too large)
        if user_preference == "direct":
            # Still need to check if dataset is too large for direct execution
            try:
                row_count = await self.spark_executor.get_table_row_count(
                    data_source, schema_name, table_name
                )
                if row_count > force_threshold:
                    logger.warning(
                        f"Dataset too large ({row_count:,} rows) for direct execution, "
                        f"forcing Spark despite user preference"
                    )
                    return "spark"
                return "direct"
            except Exception as e:
                logger.warning(f"Could not determine row count, defaulting to direct: {e}")
                return "direct"

        if user_preference == "spark":
            return "spark"

        # Auto-determine based on dataset size
        try:
            row_count = await self.spark_executor.get_table_row_count(
                data_source, schema_name, table_name
            )

            use_spark, reason = self.spark_executor.should_use_spark(
                row_count, user_preference, auto_threshold, force_threshold
            )

            mode = "spark" if use_spark else "direct"
            logger.info(f"Execution mode: {mode} - {reason}")

            return mode

        except Exception as e:
            # On error, default to direct execution
            logger.warning(f"Could not determine row count, defaulting to direct: {e}")
            return "direct"

    def _build_canonical_rule(
        self, check_type: str, config: dict[str, Any], schema_name: str, table_name: str
    ) -> dict[str, Any]:
        """
        Build canonical rule definition from node config

        Args:
            check_type: Type of check
            config: Node configuration
            schema_name: Schema name
            table_name: Table name

        Returns:
            Canonical rule definition
        """
        # Get columns - handle empty list case
        columns = config.get("columns")
        if not columns or len(columns) == 0:
            column = "*"
        else:
            # Use first column (canonical rules expect single column)
            column = columns[0]

        entity = f"{table_name}.{column}"

        if check_type == "completeness":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            # Accept checkMode (camelCase), check_mode (snake_case), or subtype — all mean the same thing
            check_mode = (
                config.get("checkMode") or config.get("check_mode") or config.get("subtype", "null")
            )

            params = {"columns": columns if columns else [column]}
            params["check_mode"] = check_mode
            params["threshold_pass"] = threshold

            # Mode-specific parameter forwarding (accept both camelCase and snake_case)
            if config.get("placeholderValues") or config.get("placeholder_values"):
                params["placeholder_values"] = config.get("placeholderValues") or config.get(
                    "placeholder_values"
                )
            if config.get("conditionColumn") or config.get("condition_column"):
                params["condition_column"] = config.get("conditionColumn") or config.get(
                    "condition_column"
                )
            if (
                config.get("conditionValue") is not None
                or config.get("condition_value") is not None
            ):
                params["condition_value"] = (
                    config.get("conditionValue")
                    if config.get("conditionValue") is not None
                    else config.get("condition_value")
                )
            if config.get("conditionOperator") or config.get("condition_operator"):
                params["condition_operator"] = config.get("conditionOperator") or config.get(
                    "condition_operator"
                )
            if config.get("multiFieldMode") or config.get("multi_field_mode"):
                params["multi_field_mode"] = config.get("multiFieldMode") or config.get(
                    "multi_field_mode"
                )
            if config.get("groupByColumns") or config.get("group_by_columns"):
                params["group_by_columns"] = config.get("groupByColumns") or config.get(
                    "group_by_columns"
                )
            if "includeEmptyStrings" in config or "include_empty_strings" in config:
                params["include_empty_strings"] = config.get(
                    "includeEmptyStrings", config.get("include_empty_strings")
                )
            if config.get("thresholdWarn") is not None or config.get("threshold_warn") is not None:
                params["threshold_warn"] = (
                    config.get("thresholdWarn")
                    if config.get("thresholdWarn") is not None
                    else config.get("threshold_warn")
                )
            if config.get("filterExpression") or config.get("filter_expression"):
                params["filter_expression"] = config.get("filterExpression") or config.get(
                    "filter_expression"
                )
            if config.get("severity"):
                params["severity"] = config["severity"]

            return {
                "dimension": "completeness",
                "entity": entity,
                "condition": "IS NOT NULL",
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "blocker"),
                "parameters": params,
            }

        elif check_type == "validity":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )

            # Built-in regex patterns for common validation types
            BUILTIN_PATTERNS = {
                "email": r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
                "phone": r"^\+?[\d\s\-\(\)]{7,20}$",
                "date": r"^\d{4}-\d{2}-\d{2}$",
            }

            # Support both old nested "rule" structure and new flat structure from the UI
            rule = config.get("rule", {}) or {}
            validation_type = config.get("validationType")

            # Infer validation_type from old config keys when not explicitly set
            if not validation_type:
                if config.get("pattern") or rule.get("pattern") or rule.get("expression"):
                    validation_type = "regex"
                elif (
                    config.get("min_value") is not None
                    or config.get("max_value") is not None
                    or rule.get("min_value") is not None
                    or rule.get("max_value") is not None
                ):
                    validation_type = "range"
                elif (
                    config.get("allowed_values")
                    or config.get("allowedValues")
                    or rule.get("allowed_values")
                ):
                    validation_type = "allowed_values"
                elif validation_type in BUILTIN_PATTERNS:
                    validation_type = "regex"
                else:
                    # Use subtype directly when set by the new UI
                    _subtype = config.get("subtype", "")
                    if _subtype in (
                        "cross_field",
                        "date_logic",
                        "business_rule",
                        "negative",
                        "reference_lookup",
                    ):
                        validation_type = _subtype
                    # Legacy key-based inference
                    elif config.get("referenceDataset") or config.get("reference_dataset"):
                        validation_type = "reference_lookup"
                    elif config.get("businessRuleExpression") or config.get(
                        "business_rule_expression"
                    ):
                        validation_type = "business_rule"
                    elif config.get("negativeExpression") or config.get("negative_pattern"):
                        validation_type = "negative"
                    elif config.get("comparisonColumn") or config.get("comparison_column"):
                        validation_type = "cross_field"
                    else:
                        validation_type = "regex"  # default fallback

            regex_pattern = (
                config.get("pattern")  # top-level pattern (current UI)
                or rule.get("pattern")  # legacy nested structure
                or rule.get("expression")  # legacy nested structure
                or BUILTIN_PATTERNS.get(config.get("validationType", ""))  # built-in type mapping
            )

            parameters = {
                "validation_type": validation_type,
                "threshold_pass": threshold,
            }

            if regex_pattern:
                parameters["regex_pattern"] = regex_pattern

            # Allowed values support
            allowed_values = (
                config.get("allowed_values")
                or config.get("allowedValues")
                or rule.get("allowed_values")
            )
            if allowed_values:
                parameters["allowed_values"] = allowed_values

            # Range support
            min_value = (
                config.get("min_value")
                if config.get("min_value") is not None
                else rule.get("min_value")
            )
            max_value = (
                config.get("max_value")
                if config.get("max_value") is not None
                else rule.get("max_value")
            )
            if min_value is not None:
                parameters["min_value"] = min_value
            if max_value is not None:
                parameters["max_value"] = max_value

            # F085 new config keys — accept both camelCase (legacy) and snake_case (new UI)

            # reference_lookup — accept both camelCase (legacy) and snake_case (new UI)
            # UUID→table resolution is done in execute() before this method is called
            ref_dataset = config.get("referenceDataset") or config.get("reference_dataset")
            if ref_dataset:
                parameters["reference_dataset"] = ref_dataset
            ref_col = config.get("referenceColumn") or config.get("reference_column")
            # Fallback: extract from join_keys[0].target (set via the KeyPairTable in the UI)
            if not ref_col:
                join_keys = config.get("join_keys") or []
                if join_keys and isinstance(join_keys, list) and len(join_keys) > 0:
                    ref_col = join_keys[0].get("target") if isinstance(join_keys[0], dict) else None
            if ref_col:
                parameters["reference_column"] = ref_col

            # business_rule
            biz_expr = config.get("businessRuleExpression") or config.get(
                "business_rule_expression"
            )
            if biz_expr:
                parameters["business_rule_expression"] = biz_expr

            # cross_field / date_logic — comparison column
            cmp_col = config.get("comparisonColumn") or config.get("comparison_column")
            if cmp_col:
                parameters["comparison_column"] = cmp_col

            # Map human-readable operator names (from UI dropdowns) → SQL operators
            _OPERATOR_MAP = {
                "equals": "=",
                "not_equals": "!=",
                "greater_than": ">",
                "less_than": "<",
                "greater_equal": ">=",
                "less_equal": "<=",
                # date_logic operators
                "before": "<",
                "after": ">",
                "same_day": "=",
                "within": "<=",
            }
            raw_op = (
                config.get("comparisonOperator")
                or config.get("comparison_operator")
                or config.get("date_operator")
            )
            if raw_op:
                parameters["comparison_operator"] = _OPERATOR_MAP.get(raw_op, raw_op)

            # negative — forward a full SQL boolean expression directly when negativeExpression
            # is provided; only transform a raw pattern when negative_pattern is used.
            neg_expr_direct = config.get("negativeExpression")
            neg_pattern = config.get("negative_pattern")
            if neg_expr_direct:
                # Already a well-formed SQL boolean expression — store as-is.
                parameters["negative_expression"] = neg_expr_direct
            elif neg_pattern:
                neg_mode = config.get("negative_match_mode", "regex")
                # Escape single quotes in pattern to prevent SQL injection
                escaped = str(neg_pattern).replace("'", "''")
                if neg_mode == "exact":
                    neg_expr_built = f"\"{column}\" = '{escaped}'"
                elif neg_mode == "contains":
                    neg_expr_built = f"\"{column}\" LIKE '%{escaped}%'"
                else:  # regex — use ~ (PostgreSQL); _adjust_for_spark_sql converts it to RLIKE
                    neg_expr_built = f"\"{column}\" ~ '{escaped}'"
                parameters["negative_expression"] = neg_expr_built

            # null_handling, case_sensitive, thresholds, filter
            null_handling = config.get("nullHandling") or config.get("null_handling")
            if null_handling:
                parameters["null_handling"] = null_handling
            if "caseSensitive" in config:
                parameters["case_sensitive"] = config["caseSensitive"]
            elif "case_sensitive" in config:
                parameters["case_sensitive"] = config["case_sensitive"]
            threshold_warn = (
                config.get("thresholdWarn")
                if config.get("thresholdWarn") is not None
                else config.get("threshold_warn")
            )
            if threshold_warn is not None:
                parameters["threshold_warn"] = threshold_warn
            filter_expr = config.get("filterExpression") or config.get("filter_expression")
            if filter_expr:
                parameters["filter_expression"] = filter_expr

            # condition is only used for display / generic SQL fallback
            condition = regex_pattern or ""

            return {
                "dimension": "validity",
                "entity": entity,
                "condition": condition,
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "blocker"),
                "parameters": parameters,
            }

        elif check_type == "uniqueness":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            uniqueness_mode = config.get("uniquenessMode") or config.get("subtype")

            # Normalize columns
            ui_columns = config.get("columns") or ([column] if column else [])

            params = {"columns": ui_columns, "threshold_pass": threshold}

            # Infer mode for backward compat — check both camelCase (legacy) and snake_case (new UI)
            if not uniqueness_mode:
                if config.get("scopeColumns") or config.get("scope_columns"):
                    uniqueness_mode = "scoped"
                elif config.get("crossDatasetName") or config.get("cross_dataset_name"):
                    uniqueness_mode = "cross_dataset"
                elif config.get("fuzzyAlgorithm") or config.get("fuzzy_algorithm"):
                    uniqueness_mode = "fuzzy"
                elif config.get("temporalWindow") or config.get("temporal_column"):
                    uniqueness_mode = "temporal"
                elif len(ui_columns) > 1:
                    uniqueness_mode = "composite"
                else:
                    uniqueness_mode = "exact"

            params["uniqueness_mode"] = uniqueness_mode

            # Forward camelCase params (legacy)
            key_map = {
                "scopeColumns": "scope_columns",
                "crossDatasetName": "cross_dataset_name",
                "crossDatasetColumn": "cross_dataset_column",
                "fuzzyAlgorithm": "fuzzy_algorithm",
                "fuzzyThreshold": "fuzzy_threshold",
                "temporalColumn": "temporal_column",
                "temporalWindow": "temporal_window",
                "nullHandling": "null_handling",
                "caseSensitive": "case_sensitive",
                "thresholdWarn": "threshold_warn",
                "filterExpression": "filter_expression",
            }
            for camel, snake in key_map.items():
                val = config.get(camel)
                if val is not None:
                    params[snake] = val

            # Forward snake_case params from new UI (don't overwrite camelCase values already set)
            for snake_key in (
                "scope_columns",
                "cross_dataset_name",
                "cross_dataset_column",
                "fuzzy_algorithm",
                "fuzzy_threshold",
                "temporal_column",
                "null_handling",
                "case_sensitive",
                "threshold_warn",
                "filter_expression",
            ):
                if config.get(snake_key) is not None and snake_key not in params:
                    params[snake_key] = config[snake_key]

            # Build temporal_window from split value+unit fields (new UI sends these separately)
            if "temporal_window" not in params:
                _tw_val = config.get("temporal_window_value")
                _tw_unit = config.get("temporal_window_unit")
                if _tw_val is not None and _tw_unit:
                    # Map UI unit names to compiler suffix letters (d/h/m/s)
                    _UNIT_MAP = {
                        "minutes": "m",
                        "hours": "h",
                        "days": "d",
                        "weeks": "d",  # convert weeks → days
                    }
                    _suffix = _UNIT_MAP.get(str(_tw_unit), "h")
                    _value = int(_tw_val)
                    if str(_tw_unit) == "weeks":
                        _value = _value * 7
                    params["temporal_window"] = f"{_value}{_suffix}"

            return {
                "dimension": "uniqueness",
                "entity": entity,
                "condition": "NO DUPLICATES",
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "blocker"),
                "parameters": params,
            }

        elif check_type == "conformity":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            # Accept both camelCase (legacy) and snake_case / "subtype" (new UI)
            conformity_type = config.get("conformityType") or config.get("subtype")

            ui_columns = config.get("columns") or ([column] if column else [])
            params = {"columns": ui_columns, "threshold_pass": threshold}

            # Infer type — check both camelCase (legacy) and snake_case (new UI) keys
            if not conformity_type:
                if config.get("regexPattern") or config.get("pattern"):
                    conformity_type = "regex"
                elif config.get("standardName") or config.get("standard_name"):
                    conformity_type = "standard"
                elif any(
                    config.get(k) is not None
                    for k in ("minLength", "maxLength", "min_length", "max_length")
                ):
                    conformity_type = "length"
                elif config.get("allowedCharacters") or config.get("allowed_charset"):
                    conformity_type = "charset"
                elif config.get("caseRule") or config.get("expected_case"):
                    conformity_type = "case"
                elif config.get("structuralFormat") or config.get("structural_pattern"):
                    conformity_type = "structural"
                else:
                    conformity_type = "regex"

            # Forward camelCase params (legacy)
            key_map = {
                "regexPattern": "regex_pattern",
                "standardName": "standard_name",
                "minLength": "min_length",
                "maxLength": "max_length",
                "allowedCharacters": "allowed_characters",
                "caseRule": "case_rule",
                "structuralFormat": "structural_format",
                "trimWhitespace": "trim_whitespace",
                "nullHandling": "null_handling",
                "thresholdWarn": "threshold_warn",
                "filterExpression": "filter_expression",
            }
            for camel, snake in key_map.items():
                val = config.get(camel)
                if val is not None:
                    params[snake] = val

            # Forward snake_case params from new UI (don't overwrite camelCase values)
            for snake_key in (
                "standard_name",
                "min_length",
                "max_length",
                "trim_whitespace",
                "null_handling",
                "threshold_warn",
                "filter_expression",
            ):
                if config.get(snake_key) is not None and snake_key not in params:
                    params[snake_key] = config[snake_key]

            # pattern → regex_pattern fallback
            if config.get("pattern") and "regex_pattern" not in params:
                params["regex_pattern"] = config["pattern"]

            # charset: map allowed_charset enum → allowed_characters char class
            if conformity_type == "charset" and "allowed_characters" not in params:
                _CHARSET_MAP = {
                    "alpha": "A-Za-z",
                    "numeric": "0-9",
                    "alphanumeric": "A-Za-z0-9",
                    "ascii": "\\x00-\\x7F",
                    "printable": "\\x20-\\x7E",
                }
                _allowed_charset = config.get("allowed_charset") or config.get("allowedCharset")
                if _allowed_charset:
                    if _allowed_charset == "custom":
                        params["allowed_characters"] = config.get("custom_charset_pattern", "")
                    else:
                        params["allowed_characters"] = _CHARSET_MAP.get(_allowed_charset, "")

            # case: map expected_case → case_rule
            if conformity_type == "case" and "case_rule" not in params:
                _expected_case = config.get("expected_case") or config.get("expectedCase")
                if _expected_case:
                    params["case_rule"] = _expected_case

            # structural: convert AA-9999 template → regex, then delegate to regex check
            # (compiler's structural_format handles json/xml, not positional templates)
            if conformity_type == "structural" and "structural_format" not in params:
                _struct_pat = config.get("structural_pattern") or config.get("structuralPattern")
                if _struct_pat:
                    _rx = "^"
                    for _ch in str(_struct_pat):
                        if _ch == "A":
                            _rx += "[A-Z]"
                        elif _ch == "9":
                            _rx += "[0-9]"
                        else:
                            _rx += re.escape(_ch)
                    _rx += "$"
                    conformity_type = "regex"
                    params["regex_pattern"] = _rx

            params["conformity_type"] = conformity_type

            return {
                "dimension": "conformity",
                "entity": entity,
                "condition": params.get("regex_pattern", ""),
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "blocker"),
                "parameters": params,
            }

        elif check_type == "consistency":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            consistency_type = config.get("consistencyType") or config.get("subtype")

            ui_columns = config.get("columns") or ([column] if column != "*" else [])
            params = {"columns": ui_columns, "threshold_pass": threshold}

            # Forward camelCase → snake_case (legacy / direct API)
            key_map = {
                "ruleExpression": "rule_expression",
                "expectedColumn": "expected_column",
                "comparisonColumn": "comparison_column",
                "comparisonColumns": "comparison_columns",
                "comparisonDataset": "comparison_dataset",
                "joinKeys": "join_keys",
                "groupByColumns": "group_by_columns",
                "aggregationFunction": "aggregation_function",
                "toleranceType": "tolerance_type",
                "toleranceValue": "tolerance_value",
                "nullHandling": "null_handling",
                "thresholdWarn": "threshold_warn",
                "filterExpression": "filter_expression",
                "operator": "operator",
                "startColumn": "start_column",
                "endColumn": "end_column",
            }
            for camel, snake in key_map.items():
                val = config.get(camel)
                if val is not None:
                    params[snake] = val

            # Forward snake_case params sent directly by the UI
            for snake_key in (
                "rule_expression",
                "expected_column",
                "comparison_column",
                "comparison_columns",
                "comparison_dataset",
                "join_keys",
                "group_by_columns",
                "aggregate_function",
                "aggregation_function",
                "tolerance_type",
                "tolerance_value",
                "null_handling",
                "threshold_warn",
                "filter_expression",
                "operator",
                "start_column",
                "end_column",
            ):
                if config.get(snake_key) is not None and snake_key not in params:
                    params[snake_key] = config[snake_key]

            # UI sends aggregate_function; compiler expects aggregation_function
            if "aggregation_function" not in params and params.get("aggregate_function"):
                params["aggregation_function"] = params["aggregate_function"]

            # Infer type if not explicit (check snake_case fields first, then camelCase)
            if not consistency_type:
                if params.get("aggregation_function") or params.get("aggregate_function"):
                    consistency_type = "aggregation"
                elif params.get("comparison_dataset") and params.get("join_keys"):
                    consistency_type = "cross_table"
                elif params.get("start_column") and params.get("end_column"):
                    consistency_type = "temporal"
                elif params.get("comparison_column"):
                    consistency_type = "temporal"
                elif params.get("group_by_columns") and params.get("comparison_columns"):
                    consistency_type = "inter_record"
                elif params.get("expected_column"):
                    consistency_type = "formula"
                elif params.get("rule_expression"):
                    consistency_type = "intra_record"
                elif params.get("reference_column"):
                    consistency_type = "intra_record"
                else:
                    consistency_type = "intra_record"

            params["consistency_type"] = consistency_type

            # Backward compat: old referenceColumn + operator → rule_expression
            ref_col = config.get("referenceColumn") or config.get("reference_column")
            if ref_col:
                op = config.get("operator", "=")
                if "rule_expression" not in params:
                    params["rule_expression"] = f'"{column}" {op} "{ref_col}"'
                params["reference_column"] = ref_col

            # Formula: expected_column is the target column (column being validated)
            if consistency_type == "formula" and "expected_column" not in params:
                params["expected_column"] = column

            # Temporal: map start_column/end_column → entity column / comparison_column
            # Semantic: end_date >= start_date (end must be after start)
            # entity = end_column, comparison_column = start_column, default op ">="
            if consistency_type == "temporal":
                _start = params.get("start_column")
                _end = params.get("end_column")
                if _end:
                    column = _end
                    entity = f"{table_name}.{_end}"
                if _start and "comparison_column" not in params:
                    params["comparison_column"] = _start

            return {
                "dimension": "consistency",
                "entity": entity,
                "condition": params.get("rule_expression", ""),
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "blocker"),
                "parameters": params,
            }

        elif check_type == "timeliness":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            # Accept timelinessType (camelCase from UI) or subtype (snake_case stored by flow builder)
            timeliness_type = config.get("timelinessType") or config.get("subtype")

            ui_columns = config.get("columns") or ([column] if column else [])
            params = {"columns": ui_columns, "threshold_pass": threshold}

            # Forward all config keys (camelCase → snake_case)
            key_map = {
                "timestampColumn": "timestamp_column",
                "comparisonTimestamp": "comparison_timestamp",
                "maxAge": "max_age",
                "metricType": "metric_type",
                "deliveryWindowStart": "delivery_window_start",
                "deliveryWindowEnd": "delivery_window_end",
                "expectedFrequency": "expected_frequency",
                "nullHandling": "null_handling",
                "thresholdWarn": "threshold_warn",
                "filterExpression": "filter_expression",
            }
            for camel, snake in key_map.items():
                val = config.get(camel)
                if val is not None:
                    params[snake] = val

            # Forward snake_case params stored directly by the flow builder
            for snake_key in (
                "timestamp_column",
                "comparison_timestamp",
                "max_age",
                "metric_type",
                "delivery_window_start",
                "delivery_window_end",
                "expected_frequency",
                "null_handling",
                "threshold_warn",
                "filter_expression",
            ):
                val = config.get(snake_key)
                if val is not None and snake_key not in params:
                    params[snake_key] = val

            # Assemble max_age string from split value+unit fields (UI stores them separately)
            _unit_map = {"hours": "h", "days": "d", "minutes": "m", "seconds": "s", "weeks": "w"}
            if "max_age" not in params:
                max_age_val = config.get("max_age_value")
                max_age_unit = config.get("max_age_unit", "hours")
                if max_age_val is not None:
                    params["max_age"] = f"{max_age_val}{_unit_map.get(max_age_unit, 'h')}"

            # Assemble expected_frequency string from split value+unit fields
            if "expected_frequency" not in params:
                freq_val = config.get("expected_frequency_value")
                freq_unit = config.get("expected_frequency_unit", "hours")
                if freq_val is not None:
                    params["expected_frequency"] = f"{freq_val}{_unit_map.get(freq_unit, 'h')}"

            # Latency: map event_timestamp_column → timestamp_column,
            #          load_timestamp_column → comparison_timestamp,
            #          max_latency_value/unit → max_age
            if "timestamp_column" not in params:
                event_ts = config.get("event_timestamp_column")
                if event_ts:
                    params["timestamp_column"] = event_ts
            if "comparison_timestamp" not in params:
                load_ts = config.get("load_timestamp_column")
                if load_ts:
                    params["comparison_timestamp"] = load_ts
            if "max_age" not in params:
                lat_val = config.get("max_latency_value")
                lat_unit = config.get("max_latency_unit", "hours")
                if lat_val is not None:
                    params["max_age"] = f"{lat_val}{_unit_map.get(lat_unit, 'h')}"

            # Processing delay: map start_timestamp_column → timestamp_column,
            #                   end_timestamp_column → comparison_timestamp,
            #                   max_delay_value/unit → max_age
            if "timestamp_column" not in params:
                start_ts = config.get("start_timestamp_column")
                if start_ts:
                    params["timestamp_column"] = start_ts
            if "comparison_timestamp" not in params:
                end_ts = config.get("end_timestamp_column")
                if end_ts:
                    params["comparison_timestamp"] = end_ts
            if "max_age" not in params:
                delay_val = config.get("max_delay_value")
                delay_unit = config.get("max_delay_unit", "hours")
                if delay_val is not None:
                    params["max_age"] = f"{delay_val}{_unit_map.get(delay_unit, 'h')}"

            # Backward compat: LLM-generated dateColumn + maxAgeDays
            date_col = config.get("dateColumn")
            if date_col and "timestamp_column" not in params:
                params["timestamp_column"] = date_col
            max_age_days = config.get("maxAgeDays")
            if max_age_days is not None and "max_age" not in params:
                params["max_age"] = f"{max_age_days}d"

            # Backward compat: old schema stored window_start/window_end
            if "delivery_window_start" not in params:
                ws = config.get("window_start")
                if ws:
                    params["delivery_window_start"] = ws
            if "delivery_window_end" not in params:
                we = config.get("window_end")
                if we:
                    params["delivery_window_end"] = we

            # Infer type if not explicit
            if not timeliness_type:
                if params.get("comparison_timestamp"):
                    timeliness_type = "latency"
                elif params.get("delivery_window_start"):
                    timeliness_type = "delivery_window"
                elif params.get("expected_frequency"):
                    timeliness_type = "heartbeat"
                else:
                    timeliness_type = "freshness"

            params["timeliness_type"] = timeliness_type

            return {
                "dimension": "timeliness",
                "entity": entity,
                "condition": "",
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "high"),
                "parameters": params,
            }

        elif check_type == "accuracy":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            accuracy_type = config.get("accuracyType") or config.get("subtype")

            ui_columns = config.get("columns") or ([column] if column != "*" else [])
            params = {"columns": ui_columns, "threshold_pass": threshold}

            # Forward camelCase config keys → snake_case (legacy / direct API usage)
            key_map = {
                "referenceDataset": "reference_dataset",
                "referenceColumn": "reference_column",
                "joinKeys": "join_keys",
                "toleranceType": "tolerance_type",
                "toleranceValue": "tolerance_value",
                "statisticalMethod": "statistical_method",
                "statisticalThreshold": "statistical_threshold",
                "outlierThreshold": "statistical_threshold",  # IQR camelCase variant
                "formula": "formula",
                "nullHandling": "null_handling",
                "thresholdWarn": "threshold_warn",
                "filterExpression": "filter_expression",
                "compareColumns": "compare_columns",
                "compareColumn": "compare_column",
                "matchType": "match_type",
            }
            for camel, snake in key_map.items():
                val = config.get(camel)
                if val is not None:
                    params[snake] = val

            # Forward snake_case params sent directly by the UI (don't overwrite camelCase already mapped)
            for snake_key in (
                "reference_dataset",
                "reference_column",
                "join_keys",
                "tolerance_type",
                "tolerance_value",
                "formula",
                "null_handling",
                "threshold_warn",
                "filter_expression",
                "compare_columns",
                "compare_column",
                "match_type",
            ):
                if config.get(snake_key) is not None and snake_key not in params:
                    params[snake_key] = config[snake_key]

            # Map UI `method` field → `statistical_method` + normalize z_score → zscore
            if "statistical_method" not in params:
                _method = config.get("method")
                if _method:
                    _METHOD_MAP = {"z_score": "zscore", "zscore": "zscore", "iqr": "iqr"}
                    params["statistical_method"] = _METHOD_MAP.get(_method, _method)

            # Map UI `outlier_threshold` → `statistical_threshold`
            if "statistical_threshold" not in params:
                _ot = config.get("outlier_threshold")
                if _ot is not None:
                    params["statistical_threshold"] = _ot

            # Normalize join_keys: KeyPair list [{source: col, target: col}] → plain string list [col]
            _jk = params.get("join_keys")
            if isinstance(_jk, list) and _jk and isinstance(_jk[0], dict):
                params["join_keys"] = [
                    k.get("source") or k.get("target")
                    for k in _jk
                    if k.get("source") or k.get("target")
                ]

            # Map compare_columns/compare_column → reference_column for join-based checks
            if "reference_column" not in params:
                _cc = params.get("compare_column") or (params.get("compare_columns") or [None])[0]
                if _cc:
                    params["reference_column"] = _cc

            # Infer accuracy type if not explicit
            if not accuracy_type:
                if params.get("statistical_method") or config.get("method"):
                    accuracy_type = "statistical"
                elif params.get("formula"):
                    accuracy_type = "derived_value"
                elif params.get("tolerance_value") is not None and params.get("reference_dataset"):
                    accuracy_type = "tolerated_deviation"
                elif params.get("reference_dataset"):
                    accuracy_type = "reference_comparison"
                else:
                    accuracy_type = "reference_comparison"  # default fallback

            params["accuracy_type"] = accuracy_type

            # If entity column is '*', derive a proper column for SQL generation
            _ent_col = column
            if _ent_col == "*":
                _ent_col = (
                    (params.get("columns") or [None])[0]
                    or params.get("reference_column")
                    or params.get("compare_column")
                    or (params.get("compare_columns") or [None])[0]
                    or column
                )
            entity = f"{table_name}.{_ent_col}"

            return {
                "dimension": "accuracy",
                "entity": entity,
                "condition": "",
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "high"),
                "parameters": params,
            }

        elif check_type == "reconciliation":
            threshold = (
                config.get("pass_threshold")
                or config.get("threshold_pass")
                or config.get("threshold", 100)
            )
            # Accept reconciliationType (camelCase) or subtype (snake_case stored by flow builder)
            recon_type = config.get("reconciliationType") or config.get("subtype")

            params = {"threshold_pass": threshold}

            # Forward camelCase keys
            key_map = {
                "sourceDataset": "source_dataset",
                "targetDataset": "target_dataset",
                "reconciliationType": "reconciliation_type",
                "joinKeys": "join_keys",
                "compareColumns": "compare_columns",
                "compareColumn": "compare_column",
                "aggregateColumn": "aggregate_column",
                "aggregateFunction": "aggregate_function",
                "toleranceType": "tolerance_type",
                "toleranceValue": "tolerance_value",
                "sourceFilter": "source_filter",
                "targetFilter": "target_filter",
                "groupByColumns": "group_by_columns",
                "thresholdWarn": "threshold_warn",
            }
            for camel, snake in key_map.items():
                val = config.get(camel)
                if val is not None:
                    params[snake] = val

            # Forward snake_case params stored directly by the flow builder
            for snake_key in (
                "source_dataset",
                "target_dataset",
                "reconciliation_type",
                "join_keys",
                "compare_columns",
                "compare_column",
                "aggregate_column",
                "aggregate_function",
                "tolerance_type",
                "tolerance_value",
                "source_filter",
                "target_filter",
                "group_by_columns",
                "null_handling",
                "threshold_warn",
                "filter_expression",
            ):
                val = config.get(snake_key)
                if val is not None and snake_key not in params:
                    params[snake_key] = val

            if recon_type:
                params["reconciliation_type"] = recon_type

            # Auto-populate source_dataset from flow entity if not explicitly set
            if not params.get("source_dataset"):
                params["source_dataset"] = (
                    f"{schema_name}.{table_name}" if schema_name else table_name
                )

            # Resolve reference_dataset UUID → target_dataset table name if not explicitly set
            if not params.get("target_dataset"):
                ref_ds_id = config.get("reference_dataset")
                if ref_ds_id:
                    try:
                        from sqlalchemy import text as _text

                        from app.models.database import SessionLocal

                        with SessionLocal() as _sess:
                            _row = _sess.execute(
                                _text(
                                    "SELECT schema_name, physical_identifier FROM control.datasets WHERE dataset_id = :dsid"
                                ),
                                {"dsid": str(ref_ds_id)},
                            ).first()
                            if _row:
                                _sch, _tbl = _row
                                params["target_dataset"] = f"{_sch}.{_tbl}" if _sch else _tbl
                    except Exception as _e:
                        logger.warning(f"Could not resolve reference_dataset {ref_ds_id}: {_e}")

            source_ds = params.get("source_dataset", "")
            return {
                "dimension": "reconciliation",
                "entity": entity if entity != f"{schema_name}.{table_name}" else source_ds,
                "condition": "",
                "expectation": str(threshold) + "%",
                "severity": config.get("severity", "critical"),
                "parameters": params,
            }

        # Default rule structure
        threshold = (
            config.get("pass_threshold")
            or config.get("threshold_pass")
            or config.get("threshold", 100)
        )
        return {
            "dimension": check_type,
            "entity": entity,
            "condition": config.get("condition", ""),
            "expectation": str(threshold) + "%",
            "severity": config.get("severity", "blocker"),
        }

    async def _execute_adhoc_check(
        self,
        context: NodeExecutionContext,
        data_source,
        compiled_sql: dict[str, str],
        canonical_rule: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute adhoc check without creating a rule record

        Args:
            context: Execution context
            data_source: Data source dict from input_data
            compiled_sql: Compiled SQL queries dict
            canonical_rule: Canonical rule definition

        Returns:
            Execution result dict
        """
        from sqlalchemy import text as sa_text

        from app.services.data_sources import credential_service as cred_svc
        from app.services.datasources.connection_manager import ConnectionManager

        # Resolve credentials from control schema using credential_reference
        ds_type = data_source.get("type", "postgresql")
        cred_ref = data_source.get("credential_reference")

        if not cred_ref:
            logger.error("❌ No credential_reference in data_source dict")
            return {
                "rows_scanned": 0,
                "rows_passed": 0,
                "rows_failed": 0,
                "pass_rate": Decimal(0),
                "violations": [],
            }

        cred_row = context.db.execute(
            sa_text("""
                SELECT encrypted_payload
                FROM control.data_source_credentials
                WHERE credential_id = CAST(:cred_id AS UUID)
                  AND superseded_at IS NULL
            """),
            {"cred_id": str(cred_ref)},
        ).fetchone()

        if not cred_row or not cred_row[0]:
            logger.error(f"❌ Credentials not found for credential_reference {cred_ref}")
            return {
                "rows_scanned": 0,
                "rows_passed": 0,
                "rows_failed": 0,
                "pass_rate": Decimal(0),
                "violations": [],
            }

        creds = cred_svc.decrypt(bytes(cred_row[0]))

        conn_manager = ConnectionManager()
        connector = await conn_manager.get_connector(
            ds_type,
            creds,  # already decrypted {host, port, database, username, password}
        )

        # Execute SQL using connector - use appropriate variant based on DB type
        # Compiler returns keys: compiled_sql, compiled_postgres, compiled_mysql, compiled_snowflake
        db_type = ds_type.lower()

        if db_type == "postgresql":
            sql_to_execute = compiled_sql.get("compiled_postgres") or compiled_sql.get(
                "compiled_sql", ""
            )
        elif db_type == "mysql":
            sql_to_execute = compiled_sql.get("compiled_mysql") or compiled_sql.get(
                "compiled_sql", ""
            )
        elif db_type == "snowflake":
            sql_to_execute = compiled_sql.get("compiled_snowflake") or compiled_sql.get(
                "compiled_sql", ""
            )
        else:
            sql_to_execute = compiled_sql.get("compiled_sql", "")

        if not sql_to_execute:
            logger.warning("No SQL to execute for adhoc check")
            return {
                "rows_scanned": 0,
                "rows_passed": 0,
                "rows_failed": 0,
                "pass_rate": Decimal(0),
                "violations": [],
            }

        logger.info(f"Executing SQL: {sql_to_execute}")
        result = await connector.execute_query(sql_to_execute)
        logger.info(f"Query result: {result}")

        # Parse result - connector returns list of dicts (rows)
        rows = result if isinstance(result, list) else []
        if not rows or len(rows) == 0:
            logger.warning("No rows returned from query")
            return {
                "rows_scanned": 0,
                "rows_passed": 0,
                "rows_failed": 0,
                "pass_rate": Decimal(0),
                "violations": [],
            }

        # Parse results based on dimension
        dimension = canonical_rule.get("dimension")

        # Dispatch to dimension-specific parser; fall back to generic shape if none matches.
        if dimension == "completeness":
            parsed = self._parse_completeness_results(rows, canonical_rule)
        elif dimension == "validity":
            parsed = self._parse_validity_results(rows, canonical_rule)
        elif dimension == "uniqueness":
            parsed = self._parse_uniqueness_results(rows, canonical_rule)
        elif dimension == "conformity":
            parsed = self._parse_conformity_results(rows, canonical_rule)
        elif dimension == "consistency":
            parsed = self._parse_consistency_results(rows, canonical_rule)
        elif dimension == "timeliness":
            parsed = self._parse_timeliness_results(rows, canonical_rule)
        elif dimension == "accuracy":
            parsed = self._parse_accuracy_results(rows, canonical_rule)
        elif dimension == "reconciliation":
            parsed = self._parse_reconciliation_results(rows, canonical_rule)
        else:
            row = rows[0]
            if dimension in ["validity", "conformity"]:
                total_rows = int(row.get("total_rows", 0))
                invalid_rows = int(row.get("invalid_rows", 0))
                passed_rows = total_rows - invalid_rows
                failed_rows = invalid_rows
            else:
                total_rows = int(row.get("total_rows", 0))
                passed_rows = int(row.get("passed_rows", total_rows))
                failed_rows = total_rows - passed_rows
            pass_rate = (
                Decimal(100)
                if total_rows == 0
                else (Decimal(passed_rows) / Decimal(total_rows)) * Decimal(100)
            )
            parsed = {
                "rows_scanned": total_rows,
                "rows_passed": passed_rows,
                "rows_failed": int(failed_rows),
                "pass_rate": pass_rate,
                "violations": [],
            }

        # F5 fix — capture sample failing rows so evidence / faulty-records UI
        # has something to show. The aggregate query above only counts; the
        # compiler also emits a per-row `violation_sql` we can sample.
        await self._attach_violation_samples(
            connector=connector,
            compiled_sql=compiled_sql,
            db_type=db_type,
            parsed=parsed,
        )
        return parsed

    async def _attach_violation_samples(
        self,
        connector,
        compiled_sql: dict[str, str],
        db_type: str,
        parsed: dict[str, Any],
        sample_limit: int = 100,
    ) -> None:
        """Run the compiler's per-row violation SQL and attach sample rows to ``parsed``.

        Safe to call when there are no failures or no violation SQL — it becomes a no-op.
        Errors are swallowed (logged) so a sampling failure never breaks the run.
        """
        try:
            rows_failed = int(parsed.get("rows_failed") or 0)
        except (TypeError, ValueError):
            rows_failed = 0
        if rows_failed <= 0:
            return
        # Skip if dimension-specific parser already produced violations
        existing = parsed.get("violations") or []
        if isinstance(existing, list) and len(existing) > 0:
            return

        # Prefer dialect-specific violation_sql; fall back to generic
        violation_sql_text = None
        for key in (
            f"violation_sql_{db_type}",
            "violation_sql",
        ):
            value = compiled_sql.get(key)
            if value:
                violation_sql_text = value
                break
        if not violation_sql_text:
            return

        try:
            limited = violation_sql_text.rstrip().rstrip(";")
            # Some compilers already include LIMIT; only append if absent.
            if " limit " not in limited.lower():
                limited = f"{limited} LIMIT {sample_limit}"
            logger.info(
                f"📋 Sampling up to {sample_limit} failing rows for evidence "
                f"(rows_failed={rows_failed})"
            )
            v_rows = await connector.execute_query(limited)
            if isinstance(v_rows, list):
                parsed["violations"] = v_rows[:sample_limit]
        except Exception as v_exc:  # noqa: BLE001
            logger.warning(f"Failed to sample violation rows: {v_exc}")

    def _parse_validity_results(self, rows, canonical_rule):
        """Parse validity check results with validation_type, null handling, and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        validation_type = parameters.get("validation_type", "regex")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")
        null_handling = parameters.get("null_handling", "fail")

        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        valid_rows = int(row.get("valid_rows", 0))
        invalid_rows = int(row.get("invalid_rows", 0))
        skipped_rows = int(row.get("skipped_rows", 0)) if null_handling == "skip" else 0

        evaluated_rows = (
            total_rows  # total_rows already accounts for skip via SQL (COUNT of non-null)
        )
        pass_rate = (
            Decimal(100)
            if evaluated_rows == 0
            else (Decimal(valid_rows) / Decimal(evaluated_rows)) * Decimal(100)
        )

        check_status = self._determine_check_status(
            float(pass_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        return {
            "rows_scanned": total_rows + skipped_rows if null_handling == "skip" else total_rows,
            "rows_passed": valid_rows,
            "rows_failed": invalid_rows,
            "evaluated_rows": evaluated_rows,
            "skipped_rows": skipped_rows,
            "pass_rate": pass_rate,
            "check_status": check_status,
            "validation_type": validation_type,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

    def _parse_uniqueness_results(self, rows, canonical_rule):
        """Parse uniqueness check results with uniqueness_mode, group stats, and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        uniqueness_mode = parameters.get("uniqueness_mode", "exact")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        duplicate_rows = int(row.get("duplicate_rows", 0))
        duplicate_groups = int(row.get("duplicate_groups", 0))
        max_group_size = int(row.get("max_group_size", 0))
        unique_rows = total_rows - duplicate_rows

        uniqueness_rate = (
            Decimal(100)
            if total_rows == 0
            else (Decimal(unique_rows) / Decimal(total_rows) * Decimal(100))
        )

        check_status = self._determine_check_status(
            float(uniqueness_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        avg_group_size = round(duplicate_rows / duplicate_groups, 2) if duplicate_groups > 0 else 0

        return {
            "rows_scanned": total_rows,
            "rows_passed": unique_rows,
            "rows_failed": duplicate_rows,
            "pass_rate": uniqueness_rate,
            "check_status": check_status,
            "uniqueness_mode": uniqueness_mode,
            "duplicate_groups": duplicate_groups,
            "max_group_size": max_group_size,
            "avg_group_size": avg_group_size,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

    def _parse_conformity_results(self, rows, canonical_rule):
        """Parse conformity check results with conformity_type and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        conformity_type = parameters.get("conformity_type", "regex")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        conforming_rows = int(row.get("conforming_rows", 0))
        non_conforming_rows = int(row.get("non_conforming_rows", 0))

        conformity_rate = (
            Decimal(100)
            if total_rows == 0
            else (Decimal(conforming_rows) / Decimal(total_rows) * Decimal(100))
        )

        check_status = self._determine_check_status(
            float(conformity_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        return {
            "rows_scanned": total_rows,
            "rows_passed": conforming_rows,
            "rows_failed": non_conforming_rows,
            "pass_rate": conformity_rate,
            "conformity_rate": conformity_rate,
            "check_status": check_status,
            "conformity_type": conformity_type,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

    def _parse_consistency_results(self, rows, canonical_rule):
        """Parse consistency check results with consistency_type and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        consistency_type = parameters.get("consistency_type", "intra_record")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        consistent_rows = int(row.get("consistent_rows", 0))
        inconsistent_rows = int(row.get("inconsistent_rows", 0))

        consistency_rate = (
            Decimal(100)
            if total_rows == 0
            else (Decimal(consistent_rows) / Decimal(total_rows) * Decimal(100))
        )

        check_status = self._determine_check_status(
            float(consistency_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        return {
            "rows_scanned": total_rows,
            "rows_passed": consistent_rows,
            "rows_failed": inconsistent_rows,
            "pass_rate": consistency_rate,
            "consistency_rate": consistency_rate,
            "check_status": check_status,
            "consistency_type": consistency_type,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

    def _parse_timeliness_results(self, rows, canonical_rule):
        """Parse timeliness check results with timeliness_type and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        timeliness_type = parameters.get("timeliness_type", "freshness")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        timely_rows = int(row.get("timely_rows", 0))
        untimely_rows = int(row.get("untimely_rows", 0))

        timeliness_rate = (
            Decimal(100)
            if total_rows == 0
            else (Decimal(timely_rows) / Decimal(total_rows) * Decimal(100))
        )

        check_status = self._determine_check_status(
            float(timeliness_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        result = {
            "rows_scanned": total_rows,
            "rows_passed": timely_rows,
            "rows_failed": untimely_rows,
            "pass_rate": timeliness_rate,
            "timeliness_rate": timeliness_rate,
            "check_status": check_status,
            "timeliness_type": timeliness_type,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

        # Include extra metadata if present in the row
        if "age_seconds" in row:
            result["data_age_seconds"] = row["age_seconds"]
        if "most_recent" in row:
            result["most_recent"] = row["most_recent"]

        return result

    def _parse_reconciliation_results(self, rows, canonical_rule):
        """Parse reconciliation check results with reconciliation_type and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        recon_type = parameters.get("reconciliation_type", "one_to_one")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        row = rows[0]
        source_count = int(row.get("source_count", 0))
        target_count = int(row.get("target_count", 0))
        matched_count = int(row.get("matched_count", 0))
        missing_in_target = int(row.get("missing_in_target", 0))
        extra_in_target = int(row.get("extra_in_target", 0))

        if recon_type == "record_count":
            max_count = max(source_count, target_count)
            min_count = min(source_count, target_count)
            match_rate = (
                Decimal(100)
                if max_count == 0
                else (Decimal(min_count) / Decimal(max_count) * Decimal(100))
            )
            total_rows = max_count
            rows_passed = min_count
            rows_failed = abs(source_count - target_count)
        elif recon_type == "aggregate":
            source_agg = row.get("source_agg")
            target_agg = row.get("target_agg")
            src_val = Decimal(str(source_agg)) if source_agg is not None else Decimal(0)
            tgt_val = Decimal(str(target_agg)) if target_agg is not None else Decimal(0)
            tol_type = parameters.get("tolerance_type", "none")
            tol_val = parameters.get("tolerance_value")
            if tol_type == "absolute" and tol_val is not None:
                match_rate = (
                    Decimal(100) if abs(src_val - tgt_val) <= Decimal(str(tol_val)) else Decimal(0)
                )
            elif tol_type == "percentage" and tol_val is not None and src_val != 0:
                pct_diff = abs(src_val - tgt_val) / abs(src_val) * Decimal(100)
                match_rate = Decimal(100) if pct_diff <= Decimal(str(tol_val)) else Decimal(0)
            else:
                match_rate = Decimal(100) if src_val == tgt_val else Decimal(0)
            total_rows = 1
            rows_passed = 1 if match_rate == Decimal(100) else 0
            rows_failed = 0 if match_rate == Decimal(100) else 1
        elif recon_type == "field_level":
            field_match = int(row.get("field_match_count", 0))
            field_mismatch = int(row.get("field_mismatch_count", 0))
            total_matched = matched_count if matched_count else field_match + field_mismatch
            match_rate = (
                Decimal(100)
                if total_matched == 0
                else (Decimal(field_match) / Decimal(total_matched) * Decimal(100))
            )
            total_rows = total_matched
            rows_passed = field_match
            rows_failed = field_mismatch
        elif recon_type == "tolerance":
            within_tol = int(row.get("within_tolerance", 0))
            outside_tol = int(row.get("outside_tolerance", 0))
            total_matched = matched_count if matched_count else within_tol + outside_tol
            match_rate = (
                Decimal(100)
                if total_matched == 0
                else (Decimal(within_tol) / Decimal(total_matched) * Decimal(100))
            )
            total_rows = total_matched
            rows_passed = within_tol
            rows_failed = outside_tol
        elif recon_type == "missing_extra":
            # SQL returns source_count, target_count, missing_in_target, extra_in_target
            total_slots = source_count + extra_in_target  # union of both sides
            mismatched = missing_in_target + extra_in_target
            matched = total_slots - mismatched
            match_rate = (
                Decimal(100)
                if total_slots == 0
                else (Decimal(matched) / Decimal(total_slots) * Decimal(100))
            )
            total_rows = total_slots
            rows_passed = matched
            rows_failed = mismatched
        else:
            # one_to_one
            max_count = max(source_count, target_count)
            match_rate = (
                Decimal(100)
                if max_count == 0
                else (Decimal(matched_count) / Decimal(max_count) * Decimal(100))
            )
            total_rows = max_count
            rows_passed = matched_count
            rows_failed = missing_in_target + extra_in_target

        check_status = self._determine_check_status(
            float(match_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        return {
            "rows_scanned": total_rows,
            "rows_passed": rows_passed,
            "rows_failed": rows_failed,
            "pass_rate": match_rate,
            "match_rate": match_rate,
            "check_status": check_status,
            "reconciliation_type": recon_type,
            "source_count": source_count,
            "target_count": target_count,
            "matched_count": matched_count,
            "missing_in_target": missing_in_target,
            "extra_in_target": extra_in_target,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

    def _parse_accuracy_results(self, rows, canonical_rule):
        """Parse accuracy check results with accuracy_type and WARN support."""
        parameters = canonical_rule.get("parameters", {})
        accuracy_type = parameters.get("accuracy_type", "reference_comparison")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        verified_rows = int(row.get("verified_rows", total_rows))
        unverifiable_rows = int(row.get("unverifiable_rows", 0))
        accurate_rows = int(row.get("accurate_rows", 0))
        inaccurate_rows = int(row.get("inaccurate_rows", 0))

        accuracy_rate = (
            Decimal(100)
            if verified_rows == 0
            else (Decimal(accurate_rows) / Decimal(verified_rows) * Decimal(100))
        )

        check_status = self._determine_check_status(
            float(accuracy_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )

        return {
            "rows_scanned": total_rows,
            "rows_passed": accurate_rows,
            "rows_failed": inaccurate_rows,
            "pass_rate": accuracy_rate,
            "accuracy_rate": accuracy_rate,
            "check_status": check_status,
            "accuracy_type": accuracy_type,
            "verified_rows": verified_rows,
            "unverifiable_rows": unverifiable_rows,
            "zero_rows": total_rows == 0,
            "violations": [],
        }

    def _parse_completeness_results(self, rows, canonical_rule):
        """Parse completeness check results with enhanced mode/threshold/group support."""
        parameters = canonical_rule.get("parameters", {})
        check_mode = parameters.get("check_mode", "null")
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")

        if check_mode == "group":
            return self._parse_group_completeness_results(rows, canonical_rule)

        # Single aggregate row
        row = rows[0]
        total_rows = int(row.get("total_rows", 0))
        null_rows = int(row.get("null_rows", 0))
        passed_rows = total_rows - null_rows
        failed_rows = null_rows
        pass_rate = (
            Decimal(100)
            if total_rows == 0
            else (Decimal(passed_rows) / Decimal(total_rows)) * Decimal(100)
        )

        check_status = self._determine_check_status(
            float(pass_rate),
            float(threshold_pass),
            float(threshold_warn) if threshold_warn is not None else None,
        )
        zero_rows = total_rows == 0

        return {
            "rows_scanned": total_rows,
            "rows_passed": passed_rows,
            "rows_failed": int(failed_rows),
            "pass_rate": pass_rate,
            "check_status": check_status,
            "check_mode": check_mode,
            "zero_rows": zero_rows,
            "violations": [],
        }

    def _parse_group_completeness_results(self, rows, canonical_rule):
        """Parse multi-row group completeness results."""
        parameters = canonical_rule.get("parameters", {})
        threshold_pass = parameters.get("threshold_pass", 100)
        threshold_warn = parameters.get("threshold_warn")
        group_by_columns = parameters.get("group_by_columns", [])

        group_results = []
        overall_total = 0
        overall_passed = 0
        worst_status = "PASS"

        for row in rows:
            total = int(row.get("total_rows", 0))
            null_count = int(row.get("null_rows", 0))
            passed = total - null_count
            rate = 100.0 if total == 0 else (passed / total) * 100
            status = self._determine_check_status(
                rate,
                float(threshold_pass),
                float(threshold_warn) if threshold_warn is not None else None,
            )

            group_key = {col: row.get(col) for col in group_by_columns}
            group_results.append(
                {
                    "group_key": group_key,
                    "total_rows": total,
                    "passed_rows": passed,
                    "failed_rows": null_count,
                    "pass_rate": round(rate, 2),
                    "check_status": status,
                }
            )

            overall_total += total
            overall_passed += passed
            worst_status = self._worst_status(worst_status, status)

        overall_rate = (
            Decimal(100)
            if overall_total == 0
            else (Decimal(overall_passed) / Decimal(overall_total)) * Decimal(100)
        )

        return {
            "rows_scanned": overall_total,
            "rows_passed": overall_passed,
            "rows_failed": overall_total - overall_passed,
            "pass_rate": overall_rate,
            "check_status": worst_status,
            "check_mode": "group",
            "zero_rows": overall_total == 0,
            "violations": [],
            "metadata": {"group_results": group_results[:100]},
        }

    @staticmethod
    def _determine_check_status(
        pass_rate: float, threshold_pass: float, threshold_warn=None
    ) -> str:
        """Determine PASS/WARN/FAIL based on thresholds."""
        if pass_rate >= threshold_pass:
            return "PASS"
        if threshold_warn is not None and pass_rate >= threshold_warn:
            return "WARN"
        return "FAIL"

    @staticmethod
    def _worst_status(current: str, new: str) -> str:
        """Return the worse of two statuses."""
        order = {"PASS": 0, "WARN": 1, "FAIL": 2, "ERROR": 3}
        return current if order.get(current, 0) >= order.get(new, 0) else new
