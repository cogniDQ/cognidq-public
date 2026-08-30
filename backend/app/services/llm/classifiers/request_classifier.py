"""
Request Classifier for Flow Builder

Analyzes incoming prompts to determine routing strategy.
"""

import logging
import re
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RequestComplexity(str, Enum):
    """Request complexity levels"""

    SIMPLE = "simple"
    COMPLEX = "complex"


class RequestClassifier:
    """
    Classifies flow builder requests to route to appropriate handler.

    Classification Criteria:
    - SIMPLE: 1-2 operations, single data source, basic checks
    - COMPLEX: 3+ operations, multi-source, reconciliation, dependencies
    """

    def __init__(self, threshold: int = 3):
        """
        Args:
            threshold: Number of instructions to trigger complex mode
        """
        self.threshold = threshold

        # Keywords for different instruction types
        self.check_type_keywords = {
            "completeness": ["completeness", "complete", "null", "empty", "missing", "blank"],
            "validity": [
                "validity",
                "valid",
                "validate",
                "format",
                "email",
                "phone",
                "date",
                "pattern",
            ],
            "uniqueness": ["uniqueness", "unique", "duplicate", "distinct", "dedup"],
            "consistency": [
                "consistency",
                "consistent",
                "cross-check",
                "cross-table",
                "cross-column",
            ],
            "conformity": ["conformity", "conform", "standard", "format", "structure"],
            "accuracy": ["accuracy", "accurate", "correct", "precision", "reference"],
            "timeliness": ["timeliness", "timely", "fresh", "stale", "age", "recent"],
            "reconciliation": [
                "reconciliation",
                "reconcile",
                "compare",
                "cross-check",
                "match between",
            ],
        }

        # Multi-source indicators
        self.multi_source_keywords = [
            "between",
            "across",
            "compare",
            "reconcile",
            "match",
            "consistency",
            "consistent",
            "and",
            "with",
            "versus",
            "vs",
        ]

        # Data source action keywords
        self.data_source_keywords = [
            "add",
            "create",
            "load",
            "import",
            "connect",
            "use",
            "table",
            "dataset",
            "source",
            "database",
        ]

    def classify(self, prompt: str) -> dict[str, Any]:
        """
        Classify request complexity.

        Args:
            prompt: User's natural language request

        Returns:
            {
                "complexity": "simple" | "complex",
                "instruction_count": int,
                "detected_check_types": List[str],
                "requires_multi_source": bool,
                "requires_data_source_creation": bool,
                "estimated_nodes": int,
                "confidence": float (0-1)
            }
        """
        prompt_lower = prompt.lower()

        # Count instructions
        instruction_count = self._count_instructions(prompt_lower)

        # Detect multi-source requirements
        requires_multi_source = self._detect_multi_source(prompt_lower)

        # Detect data source creation
        requires_data_source_creation = self._detect_data_source_creation(prompt_lower)

        # Detect check types
        detected_check_types = self._detect_check_types(prompt_lower)

        # Estimate node count
        estimated_nodes = self._estimate_nodes(
            instruction_count, requires_multi_source, requires_data_source_creation
        )

        # Determine complexity
        is_complex = self._determine_complexity(
            instruction_count,
            requires_multi_source,
            requires_data_source_creation,
            detected_check_types,
        )

        # Calculate confidence
        confidence = self._calculate_confidence(
            instruction_count, requires_multi_source, detected_check_types, prompt
        )

        result = {
            "complexity": RequestComplexity.COMPLEX if is_complex else RequestComplexity.SIMPLE,
            "instruction_count": instruction_count,
            "detected_check_types": detected_check_types,
            "requires_multi_source": requires_multi_source,
            "requires_data_source_creation": requires_data_source_creation,
            "estimated_nodes": estimated_nodes,
            "confidence": confidence,
        }

        logger.info(
            f"📊 Request classified: {result['complexity']} "
            f"(instructions={instruction_count}, confidence={confidence:.2f})"
        )

        return result

    def _count_instructions(self, prompt: str) -> int:
        """Count distinct instructions in prompt"""
        count = 0

        # Count separators (each suggests a new instruction)
        separators = [",", " and ", " then ", " also ", ";", "\n"]
        for sep in separators:
            count += prompt.count(sep)

        # Count check type keywords (each check type is likely an instruction)
        for check_type, keywords in self.check_type_keywords.items():
            for keyword in keywords:
                if keyword in prompt:
                    count += 1
                    break  # Only count once per check type

        # Count explicit numbers (e.g., "1. ", "2. ", "first", "second")
        numbered_items = re.findall(
            r"\d+\.|\bfirst\b|\bsecond\b|\bthird\b|\bfourth\b|\bfifth\b", prompt
        )
        if numbered_items:
            count = max(count, len(numbered_items))

        # Minimum 1 instruction
        return max(count, 1)

    def _detect_multi_source(self, prompt: str) -> bool:
        """Detect if request requires multiple data sources"""
        # Look for multi-source indicators - but be careful with "and" between columns

        # Strong multi-source indicators
        strong_indicators = [
            "between",
            "across",
            "compare",
            "reconcile",
            "match",
            "versus",
            "vs",
            "consistency",
            "consistent",
        ]
        for keyword in strong_indicators:
            if keyword in prompt:
                return True

        # Check for "table X and table Y" pattern
        if "table" in prompt and " and " in prompt:
            # Count how many times 'table' appears
            table_count = prompt.count("table")
            if table_count >= 2:
                return True

        # Check for "source X and source Y" pattern
        if "source" in prompt and " and " in prompt:
            source_count = prompt.count("source")
            if source_count >= 2:
                return True

        # Look for reconciliation/consistency check types
        reconciliation_indicators = ["reconciliation", "consistency", "compare", "match"]
        for indicator in reconciliation_indicators:
            if indicator in prompt:
                return True

        return False

    def _detect_data_source_creation(self, prompt: str) -> bool:
        """Detect if request asks to add/create data sources"""
        for action in ["add", "create", "load", "import", "connect"]:
            for entity in ["table", "dataset", "source", "database"]:
                if (
                    f"{action} {entity}" in prompt
                    or f"{action} a {entity}" in prompt
                    or f"{action} the {entity}" in prompt
                ):
                    return True
        return False

    def _detect_check_types(self, prompt: str) -> list[str]:
        """Detect mentioned check types"""
        detected = []
        for check_type, keywords in self.check_type_keywords.items():
            for keyword in keywords:
                if keyword in prompt:
                    detected.append(check_type)
                    break  # Only add once per check type
        return list(set(detected))  # Remove duplicates

    def _estimate_nodes(
        self,
        instruction_count: int,
        requires_multi_source: bool,
        requires_data_source_creation: bool,
    ) -> int:
        """Estimate number of nodes to be created"""
        nodes = 0

        # Data source nodes
        if requires_data_source_creation:
            nodes += 2 if requires_multi_source else 1

        # Check nodes (roughly instruction_count - data source instructions)
        nodes += max(instruction_count - (1 if requires_data_source_creation else 0), 1)

        return nodes

    def _determine_complexity(
        self,
        instruction_count: int,
        requires_multi_source: bool,
        requires_data_source_creation: bool,
        detected_check_types: list[str],
    ) -> bool:
        """Determine if request is complex"""
        # Complex if instruction count exceeds threshold
        if instruction_count >= self.threshold:
            return True

        # Complex if multi-source
        if requires_multi_source:
            return True

        # Complex if creating sources AND adding checks
        if requires_data_source_creation and instruction_count > 1:
            return True

        # Complex if reconciliation check is involved
        if "reconciliation" in detected_check_types or "consistency" in detected_check_types:
            return True

        return False

    def _calculate_confidence(
        self,
        instruction_count: int,
        requires_multi_source: bool,
        detected_check_types: list[str],
        prompt: str,
    ) -> float:
        """Calculate classification confidence (0-1)"""
        confidence = 0.5  # Base confidence

        # Increase confidence if clear indicators present
        if instruction_count >= self.threshold:
            confidence += 0.2

        if requires_multi_source:
            confidence += 0.15

        if len(detected_check_types) > 0:
            confidence += 0.1 * min(len(detected_check_types), 3)

        # Increase if prompt is detailed (>50 chars)
        if len(prompt) > 50:
            confidence += 0.1

        # Decrease if very short/vague
        if len(prompt) < 20:
            confidence -= 0.2

        return min(max(confidence, 0.0), 1.0)


# Singleton instance
request_classifier = RequestClassifier()
