"""
Packet 4 — Unit tests: query parameter validator and ILIKE escaper
==================================================================

Tests for:
    * ``escape_ilike_term``         — TDD §3.3 ILIKE metacharacter escaping
    * ``parse_list_tenants_query``  — all query parameter validation rules

No database or HTTP dependency.  All 422-producing paths are asserted by
catching ``TenantAPIError`` and checking ``.code`` and ``.fields``.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/unit/services/f001/test_p4_list_tenants_query.py -v
"""

from __future__ import annotations

import pytest
from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.tenants.queries import (
    escape_ilike_term,
    parse_list_tenants_query,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raises(
    *,
    expected_code: str,
    expected_status: int = 422,
    **parse_kwargs,
) -> TenantAPIError:
    """Assert that parse_list_tenants_query raises TenantAPIError with given code."""
    with pytest.raises(TenantAPIError) as exc_info:
        parse_list_tenants_query(**parse_kwargs)
    err: TenantAPIError = exc_info.value
    assert err.code == expected_code, (
        f"Expected code={expected_code!r} but got {err.code!r}. message={err.message!r}"
    )
    assert err.status_code == expected_status
    return err


def _ok(**parse_kwargs):
    """Assert that parse_list_tenants_query succeeds and return the result."""
    return parse_list_tenants_query(**parse_kwargs)


# ===========================================================================
# escape_ilike_term
# ===========================================================================


class TestEscapeIlikeTerm:
    def test_percent_is_escaped(self):
        assert escape_ilike_term("50%") == "50\\%"

    def test_underscore_is_escaped(self):
        assert escape_ilike_term("a_b") == "a\\_b"

    def test_backslash_is_escaped(self):
        assert escape_ilike_term("C:\\dir") == "C:\\\\dir"

    def test_mixed_metacharacters_escaped(self):
        assert escape_ilike_term("%test_value") == "\\%test\\_value"

    def test_plain_string_unchanged(self):
        assert escape_ilike_term("hello world") == "hello world"

    def test_unicode_string_unchanged(self):
        assert escape_ilike_term("caf\u00e9") == "caf\u00e9"

    def test_backslash_escaped_before_percent(self):
        # "\\%" should become "\\\\%" not "\\\\\\%" (backslash is replaced first)
        assert escape_ilike_term("\\%") == "\\\\\\%"

    def test_empty_string_unchanged(self):
        assert escape_ilike_term("") == ""

    def test_all_three_metacharacters(self):
        assert escape_ilike_term("%_\\") == "\\%\\_\\\\"


# ===========================================================================
# parse_list_tenants_query — defaults
# ===========================================================================


class TestDefaults:
    def test_all_none_applies_defaults(self):
        q = _ok()
        assert q.sort_by == "created_at"
        assert q.sort_dir == "desc"
        assert q.page == 1
        assert q.page_size == 25
        assert q.include_archived is False
        assert q.status is None
        assert q.region is None
        assert q.plan is None
        assert q.q is None

    def test_empty_strings_apply_defaults(self):
        q = _ok(
            sort_by="",
            sort_dir="",
            page_str="",
            page_size_str="",
            include_archived_str="",
        )
        assert q.sort_by == "created_at"
        assert q.sort_dir == "desc"
        assert q.page == 1
        assert q.page_size == 25
        assert q.include_archived is False


# ===========================================================================
# parse_list_tenants_query — sort_by
# ===========================================================================


class TestSortBy:
    def test_created_at_accepted(self):
        q = _ok(sort_by="created_at")
        assert q.sort_by == "created_at"

    def test_updated_at_accepted(self):
        q = _ok(sort_by="updated_at")
        assert q.sort_by == "updated_at"

    def test_uppercase_normalised(self):
        q = _ok(sort_by="CREATED_AT")
        assert q.sort_by == "created_at"

    def test_invalid_sort_by_raises(self):
        _raises(sort_by="tenant_name", expected_code="invalid_sort_field")

    def test_arbitrary_string_raises(self):
        _raises(sort_by="name; DROP TABLE tenants--", expected_code="invalid_sort_field")


# ===========================================================================
# parse_list_tenants_query — sort_dir
# ===========================================================================


class TestSortDir:
    def test_asc_accepted(self):
        q = _ok(sort_dir="asc")
        assert q.sort_dir == "asc"

    def test_desc_accepted(self):
        q = _ok(sort_dir="desc")
        assert q.sort_dir == "desc"

    def test_uppercase_normalised(self):
        q = _ok(sort_dir="ASC")
        assert q.sort_dir == "asc"

    def test_invalid_sort_dir_raises(self):
        err = _raises(sort_dir="upward", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "sort_dir" for f in err.fields)


# ===========================================================================
# parse_list_tenants_query — page
# ===========================================================================


class TestPage:
    def test_valid_page_accepted(self):
        q = _ok(page_str="3")
        assert q.page == 3

    def test_page_1_accepted(self):
        q = _ok(page_str="1")
        assert q.page == 1

    def test_page_zero_raises(self):
        err = _raises(page_str="0", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page" for f in err.fields)

    def test_page_negative_raises(self):
        err = _raises(page_str="-1", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page" for f in err.fields)

    def test_page_non_integer_raises(self):
        err = _raises(page_str="abc", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page" for f in err.fields)

    def test_page_float_raises(self):
        err = _raises(page_str="1.5", expected_code="validation_error")
        assert err.fields is not None


# ===========================================================================
# parse_list_tenants_query — page_size
# ===========================================================================


class TestPageSize:
    def test_valid_page_size_accepted(self):
        q = _ok(page_size_str="10")
        assert q.page_size == 10

    def test_page_size_1_accepted(self):
        q = _ok(page_size_str="1")
        assert q.page_size == 1

    def test_page_size_100_accepted(self):
        q = _ok(page_size_str="100")
        assert q.page_size == 100

    def test_page_size_0_raises(self):
        err = _raises(page_size_str="0", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page_size" for f in err.fields)

    def test_page_size_over_100_raises(self):
        err = _raises(page_size_str="101", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page_size" for f in err.fields)

    def test_page_size_200_raises(self):
        err = _raises(page_size_str="200", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page_size" for f in err.fields)

    def test_page_size_non_integer_raises(self):
        err = _raises(page_size_str="ten", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "page_size" for f in err.fields)


# ===========================================================================
# parse_list_tenants_query — status filter
# ===========================================================================


class TestStatusFilter:
    @pytest.mark.parametrize("s", ["draft", "active", "suspended", "archived"])
    def test_all_valid_statuses_accepted(self, s: str):
        q = _ok(status=s)
        assert q.status == s

    def test_uppercase_normalised(self):
        q = _ok(status="ACTIVE")
        assert q.status == "active"

    def test_whitespace_stripped(self):
        q = _ok(status="  draft  ")
        assert q.status == "draft"

    def test_invalid_status_raises(self):
        err = _raises(status="enabled", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "status" for f in err.fields)

    def test_none_status_is_absent(self):
        q = _ok(status=None)
        assert q.status is None

    def test_empty_string_status_is_absent(self):
        q = _ok(status="   ")
        assert q.status is None


# ===========================================================================
# parse_list_tenants_query — region filter
# ===========================================================================


class TestRegionFilter:
    @pytest.mark.parametrize("r", ["eu-west", "eu-central", "us-east", "us-west"])
    def test_all_valid_regions_accepted(self, r: str):
        q = _ok(region=r)
        assert q.region == r

    def test_invalid_region_raises(self):
        err = _raises(region="ap-southeast", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "region" for f in err.fields)


# ===========================================================================
# parse_list_tenants_query — plan filter
# ===========================================================================


class TestPlanFilter:
    @pytest.mark.parametrize("p", ["starter", "growth", "enterprise"])
    def test_all_valid_plans_accepted(self, p: str):
        q = _ok(plan=p)
        assert q.plan == p

    def test_invalid_plan_raises(self):
        err = _raises(plan="premium", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "plan" for f in err.fields)


# ===========================================================================
# parse_list_tenants_query — q search term
# ===========================================================================


class TestSearchQ:
    def test_valid_q_preserved(self):
        q = _ok(q="corp")
        assert q.q == "corp"

    def test_q_stripped(self):
        q = _ok(q="  corp  ")
        assert q.q == "corp"

    def test_whitespace_only_q_becomes_none(self):
        q = _ok(q="   ")
        assert q.q is None

    def test_none_q_stays_none(self):
        q = _ok(q=None)
        assert q.q is None


# ===========================================================================
# parse_list_tenants_query — include_archived
# ===========================================================================


class TestIncludeArchived:
    def test_none_defaults_to_false(self):
        q = _ok(include_archived_str=None)
        assert q.include_archived is False

    def test_empty_string_defaults_to_false(self):
        q = _ok(include_archived_str="")
        assert q.include_archived is False

    def test_true_string_sets_true(self):
        q = _ok(include_archived_str="true")
        assert q.include_archived is True

    def test_true_uppercase(self):
        q = _ok(include_archived_str="TRUE")
        assert q.include_archived is True

    def test_one_string_sets_true(self):
        q = _ok(include_archived_str="1")
        assert q.include_archived is True

    def test_false_string_sets_false(self):
        q = _ok(include_archived_str="false")
        assert q.include_archived is False

    def test_zero_string_sets_false(self):
        q = _ok(include_archived_str="0")
        assert q.include_archived is False

    def test_invalid_value_raises(self):
        err = _raises(include_archived_str="yes", expected_code="validation_error")
        assert err.fields is not None
        assert any(f["field"] == "include_archived" for f in err.fields)
