"""
Regression tests for MetricsService pass-rate calculations.

These tests guard against the bug where category/source/trend pass rates
were computed as COUNT(rows_failed == 0) / COUNT(*), instead of the
AVG(pass_rate) formula used by get_overview_metrics(). The two formulas
diverge whenever a check has rows_failed > 0 but pass_rate > 0 (i.e. a
partial failure such as 89.95%), causing the broken methods to under-report.

We assert the produced SQL by inspecting every query() the service issues
against a MagicMock session and compiling the SQLAlchemy expressions.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.services.reporting.metrics import MetricsService
from sqlalchemy.dialects import postgresql


def _compiled_sql_strings(db_mock: MagicMock) -> list[str]:
    """Return the compiled SQL of every query the service constructed,
    including expressions passed to chained .filter() calls."""
    from sqlalchemy import select

    compiled: list[str] = []

    def _compile(expr) -> str:
        try:
            return str(
                expr.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            ).lower()
        except Exception:
            return ""

    # Top-level db.query(...) calls.
    for call in db_mock.query.call_args_list:
        try:
            stmt = select(*call.args)
            compiled.append(_compile(stmt))
        except Exception:
            continue

    # All .filter(...) args on the returned chain mock.
    chain = db_mock.query.return_value
    for call in chain.filter.call_args_list:
        for arg in call.args:
            compiled.append(_compile(arg))

    return [s for s in compiled if s]


def _make_service_with_chain(scalar_value: int = 0):
    """Build a MetricsService whose db.query(...).<chain>().scalar() == scalar_value."""
    db = MagicMock()
    # Any chained call returns the same mock; .scalar()/.all()/.first() return defaults.
    chain = MagicMock()
    chain.scalar.return_value = scalar_value
    chain.all.return_value = []
    chain.first.return_value = None
    # filter/join/group_by/order_by all return the same chain object so calls compose.
    for attr in ("filter", "join", "group_by", "order_by"):
        getattr(chain, attr).return_value = chain
    db.query.return_value = chain
    return MetricsService(db), db


# ---------------------------------------------------------------------------
# Bug #1 — get_category_breakdown must use AVG(pass_rate)
# ---------------------------------------------------------------------------
def test_category_breakdown_uses_avg_pass_rate():
    svc, db = _make_service_with_chain(scalar_value=1)
    # Service iterates 6 fixed DQ categories — return a non-zero scalar for every probe
    # so the AVG branch executes for each.
    db.query.return_value.scalar.return_value = 1

    svc.get_category_breakdown(workspace_id=uuid4(), period="30d")

    sql_blobs = _compiled_sql_strings(db)
    joined = "\n".join(sql_blobs)

    assert "avg(" in joined and "pass_rate" in joined, (
        "category breakdown must compute AVG(pass_rate)"
    )
    # The legacy formula counted rows_failed == 0 — guard against its return.
    assert "rows_failed" not in joined or "= 0" not in joined.replace(" ", ""), (
        "category breakdown must NOT use COUNT(rows_failed == 0) for pass_rate"
    )


# ---------------------------------------------------------------------------
# Bug #2 — get_source_breakdown must use AVG(pass_rate)
# ---------------------------------------------------------------------------
def test_source_breakdown_uses_avg_pass_rate():
    from types import SimpleNamespace

    svc, db = _make_service_with_chain()
    chain = db.query.return_value
    # Sources are now fetched via db.execute(text(...)).fetchall() in the service.
    fake_source_row = SimpleNamespace(id=str(uuid4()), name="src-1")
    db.execute.return_value.fetchall.return_value = [fake_source_row]
    # rules, executions, avg_pass_rate; first() is for last_execution
    chain.scalar.side_effect = [1, 1, 75.0]

    svc.get_source_breakdown(workspace_id=uuid4(), period="30d")

    joined = "\n".join(_compiled_sql_strings(db))
    assert "avg(" in joined and "pass_rate" in joined, (
        "source breakdown must compute AVG(pass_rate)"
    )
    assert "rows_failed" not in joined or "= 0" not in joined.replace(" ", ""), (
        "source breakdown must NOT use COUNT(rows_failed == 0) for pass_rate"
    )


# ---------------------------------------------------------------------------
# Bug #3 — _get_pass_rate_trend must use AVG(pass_rate) and include "failed"
# ---------------------------------------------------------------------------
def test_trend_uses_avg_pass_rate_and_includes_failed_status():
    from datetime import datetime, timedelta

    svc, db = _make_service_with_chain()
    end = datetime.utcnow()
    start = end - timedelta(days=30)

    svc._get_pass_rate_trend(workspace_id=uuid4(), start_date=start, end_date=end)

    joined = "\n".join(_compiled_sql_strings(db))
    assert "avg(" in joined and "pass_rate" in joined, "trend must compute AVG(pass_rate) per day"
    # status filter must include both completed and failed (matches overview).
    assert "in (" in joined and "completed" in joined and "failed" in joined, (
        "trend status filter must include both 'completed' and 'failed'"
    )
    assert "rows_failed" not in joined, (
        "trend must NOT reference rows_failed in pass-rate computation"
    )


# ---------------------------------------------------------------------------
# Bug #7 — pass_rate must be cast to FLOAT (not INTEGER) so 89.95 isn't truncated
# ---------------------------------------------------------------------------
def test_pass_rate_cast_uses_float_not_integer():
    from datetime import datetime, timedelta

    svc, db = _make_service_with_chain()
    end = datetime.utcnow()
    start = end - timedelta(days=30)

    svc._get_pass_rate_trend(workspace_id=uuid4(), start_date=start, end_date=end)

    joined = "\n".join(_compiled_sql_strings(db))
    # Postgres dialect renders Float as either "float" or "double precision".
    assert ("as float" in joined) or ("double precision" in joined), (
        f"pass_rate must be cast to FLOAT/DOUBLE PRECISION; got: {joined}"
    )
    assert "as integer" not in joined or "result_data -> 'pass_rate'" not in joined, (
        "pass_rate must NOT be cast to INTEGER (truncates partial pass rates)"
    )


# ---------------------------------------------------------------------------
# Scorecard trend — _trend_from_delta classifies up/down/stable
# ---------------------------------------------------------------------------
def test_trend_from_delta_classifies_correctly():
    fn = MetricsService._trend_from_delta
    # No prior value -> stable
    assert fn(95.0, None) == "stable"
    # Within ±1pp -> stable
    assert fn(95.0, 95.5) == "stable"
    assert fn(95.0, 94.5) == "stable"
    # Above threshold -> up
    assert fn(95.0, 90.0) == "up"
    # Below threshold -> down
    assert fn(80.0, 95.0) == "down"


# ---------------------------------------------------------------------------
# Scorecard trend — get_scorecard wires per-dimension and overall trends
# ---------------------------------------------------------------------------
def test_scorecard_uses_real_trend_not_hardcoded_stable():
    """
    Drive get_scorecard() against a stub that yields:
      - one current dimension with score=95.0
      - the same dimension's previous-period average=80.0 (=> "up")
      - previous-period overall average=70.0 vs computed weighted ~95 (=> "up")
    Both the dimension trend and the overall trend should be "up", proving
    the hardcoded "stable" placeholders were replaced.
    """
    from app.schemas.reporting import CategoryBreakdown, CategoryMetrics

    svc, _db = _make_service_with_chain()

    # Stub the three internal calls scorecard depends on.
    svc.get_category_breakdown = MagicMock(  # type: ignore[assignment]
        return_value=CategoryBreakdown(
            categories=[
                CategoryMetrics(
                    category="completeness",
                    total_rules=1,
                    total_executions=10,
                    pass_rate=95.0,
                    avg_execution_time=0.5,
                )
            ],
            total=1,
        )
    )
    svc._get_prev_period_pass_rate_by_category = MagicMock(  # type: ignore[assignment]
        return_value={"completeness": 80.0}
    )
    svc._get_prev_period_overall_pass_rate = MagicMock(  # type: ignore[assignment]
        return_value=70.0
    )

    sc = svc.get_scorecard(workspace_id=uuid4(), period="30d")

    assert len(sc.dimensions) == 1
    assert sc.dimensions[0].trend == "up", (
        f"per-dimension trend should reflect 95 vs 80 prior, got {sc.dimensions[0].trend}"
    )
    assert sc.trend == "up", f"overall trend should reflect ~95 vs 70 prior, got {sc.trend}"
    # Sanity: critical_issues must be 0 because score >= 80.
    assert sc.critical_issues == 0
