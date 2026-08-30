"""
Test JSON sanitization utilities
"""

from decimal import Decimal

from app.utils.json_utils import sanitize_for_json, sanitize_result_data


def test_nan_sanitization():
    """Test NaN values are converted to None"""
    data = {
        "normal_value": 42,
        "nan_value": float("nan"),
        "inf_value": float("inf"),
        "neg_inf": float("-inf"),
        "nested": {"inner_nan": float("nan"), "inner_normal": "test"},
        "list_with_nan": [1, 2, float("nan"), 3],
        "decimal_nan": Decimal("NaN"),
    }

    result = sanitize_for_json(data)

    assert result["normal_value"] == 42
    assert result["nan_value"] is None
    assert result["inf_value"] is None
    assert result["neg_inf"] is None
    assert result["nested"]["inner_nan"] is None
    assert result["nested"]["inner_normal"] == "test"
    assert result["list_with_nan"] == [1, 2, None, 3]
    assert result["decimal_nan"] is None

    print("✅ All NaN sanitization tests passed!")


def test_violation_data_sanitization():
    """Test sanitization of violations with NaN values (the actual use case)"""
    result_data = {
        "check_type": "completeness",
        "rows_scanned": 100,
        "pass_rate": 95.5,
        "violations": [
            {
                "row_id": "123",
                "gt_rule_active_dates": 1.0,
                "gt_rule_active_enddate_empty": float("nan"),  # This was causing the error!
                "other_field": "value",
            },
            {"row_id": "456", "some_metric": float("inf"), "another_field": 42},
        ],
    }

    sanitized = sanitize_result_data(result_data)

    assert sanitized["pass_rate"] == 95.5
    assert sanitized["violations"][0]["gt_rule_active_enddate_empty"] is None  # NaN -> None
    assert sanitized["violations"][0]["gt_rule_active_dates"] == 1.0
    assert sanitized["violations"][1]["some_metric"] is None  # Inf -> None
    assert sanitized["violations"][1]["another_field"] == 42

    print("✅ Violation data sanitization test passed!")
    print(f"\nSanitized violations: {sanitized['violations']}")


if __name__ == "__main__":
    test_nan_sanitization()
    test_violation_data_sanitization()
    print("\n🎉 All tests passed! NaN values will be properly handled.")
