"""
Data Profiler

Auto-profile data on ingestion to detect types, calculate statistics,
and suggest data quality checks.
"""

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


class ColumnProfile:
    """Profile statistics for a single column."""

    def __init__(self, name: str, data_type: str):
        self.name = name
        self.data_type = data_type
        self.total_count = 0
        self.null_count = 0
        self.null_percentage = 0.0
        self.unique_count = 0
        self.cardinality = 0.0  # unique_count / total_count

        # Type-specific stats
        self.min_value: Any | None = None
        self.max_value: Any | None = None
        self.mean: float | None = None
        self.median: float | None = None
        self.std_dev: float | None = None
        self.distinct_values: list[Any] = []
        self.top_values: list[dict[str, Any]] = []

        # Suggested quality checks
        self.suggested_checks: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "total_count": self.total_count,
            "null_count": self.null_count,
            "null_percentage": round(self.null_percentage, 2),
            "unique_count": self.unique_count,
            "cardinality": round(self.cardinality, 4),
            "min_value": self._serialize_value(self.min_value),
            "max_value": self._serialize_value(self.max_value),
            "mean": round(self.mean, 2) if self.mean is not None else None,
            "median": round(self.median, 2) if self.median is not None else None,
            "std_dev": round(self.std_dev, 2) if self.std_dev is not None else None,
            "distinct_values": [self._serialize_value(v) for v in self.distinct_values],
            "top_values": self.top_values,
            "suggested_checks": self.suggested_checks,
        }

    def _serialize_value(self, val: Any) -> Any:
        """Convert value to JSON-serializable format."""
        if val is None or pd.isna(val):
            return None
        if isinstance(val, (pd.Timestamp, datetime)):
            return val.isoformat()
        if isinstance(val, np.integer):
            return int(val)
        if isinstance(val, np.floating):
            return float(val)
        if hasattr(val, "item"):
            return val.item()
        return val


class DataProfiler:
    """Service for profiling datasets."""

    def __init__(self, max_distinct_values: int = 10, max_top_values: int = 5):
        self.max_distinct_values = max_distinct_values
        self.max_top_values = max_top_values

    def profile_dataframe(self, df: pd.DataFrame, actual_row_count: int = None) -> dict[str, Any]:
        """
        Profile a pandas DataFrame.

        Args:
            df: DataFrame to profile (may be a sample)
            actual_row_count: Actual total row count (if df is a sample)

        Returns:
            Dictionary with profiling results
        """
        column_profiles = []

        for column in df.columns:
            profile = self.profile_column(df[column])
            column_profiles.append(profile.to_dict())

        return {
            "total_rows": actual_row_count if actual_row_count is not None else len(df),
            "total_columns": len(df.columns),
            "columns": column_profiles,
            "profiled_at": datetime.utcnow().isoformat(),
        }

    def profile_column(self, series: pd.Series) -> ColumnProfile:
        """
        Profile a single column.

        Args:
            series: Pandas Series to profile

        Returns:
            ColumnProfile with statistics
        """
        profile = ColumnProfile(name=str(series.name), data_type=self._infer_type(series))

        # Basic stats
        profile.total_count = len(series)
        profile.null_count = int(series.isna().sum())
        profile.null_percentage = (
            (profile.null_count / profile.total_count * 100) if profile.total_count > 0 else 0
        )
        profile.unique_count = int(series.nunique())
        profile.cardinality = (
            profile.unique_count / profile.total_count if profile.total_count > 0 else 0
        )

        # Non-null values for further analysis
        non_null = series.dropna()

        if len(non_null) == 0:
            # All null - suggest null check
            profile.suggested_checks = ["null_check", "completeness_check"]
            return profile

        # Type-specific profiling
        if profile.data_type in ["integer", "float"]:
            self._profile_numeric(non_null, profile)
        elif profile.data_type == "string":
            self._profile_string(non_null, profile)
        elif profile.data_type in ["date", "datetime"]:
            self._profile_datetime(non_null, profile)
        elif profile.data_type == "boolean":
            self._profile_boolean(non_null, profile)

        # Suggest quality checks based on profile
        self._suggest_checks(profile)

        return profile

    def _infer_type(self, series: pd.Series) -> str:
        """Infer column data type."""
        if pd.api.types.is_integer_dtype(series):
            return "integer"
        elif pd.api.types.is_float_dtype(series):
            return "float"
        elif pd.api.types.is_bool_dtype(series):
            return "boolean"
        elif pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"

        # For object types, sample to infer
        non_null = series.dropna()
        if len(non_null) == 0:
            return "string"

        sample = non_null.head(100)

        # Try datetime
        try:
            pd.to_datetime(sample, errors="raise")
            return "datetime"
        except:
            pass

        # Try numeric
        try:
            numeric = pd.to_numeric(sample, errors="raise")
            if (numeric % 1 == 0).all():
                return "integer"
            return "float"
        except:
            pass

        return "string"

    def _profile_numeric(self, series: pd.Series, profile: ColumnProfile) -> None:
        """Profile numeric column."""
        try:
            numeric = pd.to_numeric(series, errors="coerce").dropna()

            if len(numeric) > 0:
                profile.min_value = numeric.min()
                profile.max_value = numeric.max()
                profile.mean = float(numeric.mean())
                profile.median = float(numeric.median())
                profile.std_dev = float(numeric.std())

                # Get top values with counts
                value_counts = series.value_counts().head(self.max_top_values)
                profile.top_values = [
                    {"value": self._serialize_value(val), "count": int(count)}
                    for val, count in value_counts.items()
                ]
        except Exception:
            pass

    def _profile_string(self, series: pd.Series, profile: ColumnProfile) -> None:
        """Profile string column."""
        # Get distinct values (limited)
        distinct = series.unique()[: self.max_distinct_values]
        profile.distinct_values = distinct.tolist()

        # Get top values with counts
        value_counts = series.value_counts().head(self.max_top_values)
        profile.top_values = [
            {"value": str(val), "count": int(count)} for val, count in value_counts.items()
        ]

        # String length stats
        try:
            lengths = series.astype(str).str.len()
            profile.min_value = int(lengths.min())
            profile.max_value = int(lengths.max())
            profile.mean = float(lengths.mean())
        except Exception:
            pass

    def _profile_datetime(self, series: pd.Series, profile: ColumnProfile) -> None:
        """Profile datetime column."""
        try:
            dt_series = pd.to_datetime(series, errors="coerce").dropna()

            if len(dt_series) > 0:
                profile.min_value = dt_series.min()
                profile.max_value = dt_series.max()
        except Exception:
            pass

    def _profile_boolean(self, series: pd.Series, profile: ColumnProfile) -> None:
        """Profile boolean column."""
        # Get value counts
        value_counts = series.value_counts()
        profile.top_values = [
            {"value": bool(val), "count": int(count)} for val, count in value_counts.items()
        ]

    def _suggest_checks(self, profile: ColumnProfile) -> None:
        """Suggest data quality checks based on profile."""
        checks = []

        # Null checks
        if profile.null_percentage > 0:
            if profile.null_percentage > 50:
                checks.append("high_null_rate")
            checks.append("null_check")
        else:
            checks.append("not_null_check")

        # Uniqueness checks
        if profile.cardinality == 1.0:
            checks.append("unique_check")
        elif profile.cardinality > 0.9:
            checks.append("high_cardinality")
        elif profile.cardinality < 0.01:
            checks.append("low_cardinality")

        # Type-specific checks
        if profile.data_type in ["integer", "float"]:
            checks.append("range_check")
            if profile.min_value is not None and profile.min_value >= 0:
                checks.append("positive_check")

        elif profile.data_type == "string":
            if profile.max_value is not None:  # max length
                checks.append("length_check")
            if profile.unique_count <= 20:
                checks.append("allowed_values_check")

        elif profile.data_type in ["date", "datetime"]:
            checks.append("date_range_check")
            checks.append("future_date_check")

        profile.suggested_checks = checks

    def _serialize_value(self, val: Any) -> Any:
        """Convert value to JSON-serializable format."""
        if val is None or pd.isna(val):
            return None
        if isinstance(val, (pd.Timestamp, datetime)):
            return val.isoformat()
        if isinstance(val, np.integer):
            return int(val)
        if isinstance(val, np.floating):
            return float(val)
        if hasattr(val, "item"):
            return val.item()
        return val
