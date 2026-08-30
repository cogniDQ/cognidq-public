"""
Unit tests — F004 P02: Data Source Validation Layer

Tests every validation function in data_source_validation without any
database or I/O.

Test IDs: VAL-01 through VAL-28
"""

import pytest
from app.services.data_sources.models import (
    BIGQUERY_SERVICE_ACCOUNT_REQUIRED_KEYS,
    SUPPORTED_SOURCE_TYPES,
)
from app.services.data_sources.validation import (
    ValidationResult,
    validate_connection_mode,
    validate_create_payload,
    validate_credential_structure,
    validate_description,
    validate_environment,
    validate_host_not_private,
    validate_immutable_fields_not_changed,
    validate_port,
    validate_source_name,
    validate_source_type,
)

# ─────────────────────────────────────────────────────────────────────────────
# VAL-01: validate_source_name — valid name
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSourceName:
    """VAL-01 through VAL-04"""

    def test_valid_name(self):
        assert validate_source_name("production-db") == []

    def test_name_with_leading_trailing_whitespace(self):
        assert validate_source_name("  my db  ") == []

    def test_empty_string_rejected(self):
        errors = validate_source_name("")
        assert any(e["field"] == "source_name" for e in errors)

    def test_whitespace_only_rejected(self):
        errors = validate_source_name("   ")
        assert any(e["field"] == "source_name" for e in errors)

    def test_max_100_chars_accepted(self):
        assert validate_source_name("x" * 100) == []

    def test_101_chars_rejected(self):
        errors = validate_source_name("x" * 101)
        assert any(e["field"] == "source_name" for e in errors)

    def test_non_string_rejected(self):
        errors = validate_source_name(123)
        assert any(e["field"] == "source_name" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-05: validate_source_type
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateSourceType:
    """VAL-05"""

    def test_all_valid_types_accepted(self):
        for stype in SUPPORTED_SOURCE_TYPES:
            assert validate_source_type(stype) == []

    def test_mongodb_rejected(self):
        errors = validate_source_type("mongodb")
        assert any(e["field"] == "source_type" for e in errors)

    def test_empty_rejected(self):
        errors = validate_source_type("")
        assert any(e["field"] == "source_type" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-06: validate_connection_mode
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateConnectionMode:
    """VAL-06"""

    def test_direct_accepted(self):
        assert validate_connection_mode("direct") == []

    def test_agent_accepted(self):
        assert validate_connection_mode("agent") == []

    def test_tunnel_rejected(self):
        errors = validate_connection_mode("tunnel")
        assert any(e["field"] == "connection_mode" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-07: validate_environment
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateEnvironment:
    """VAL-07"""

    def test_all_valid_environments_accepted(self):
        for env in ("development", "staging", "production"):
            assert validate_environment(env) == []

    def test_disaster_recovery_rejected(self):
        errors = validate_environment("disaster-recovery")
        assert any(e["field"] == "environment" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-08: validate_description
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateDescription:
    """VAL-08"""

    def test_none_accepted(self):
        assert validate_description(None) == []

    def test_valid_string_accepted(self):
        assert validate_description("A useful description.") == []

    def test_500_chars_accepted(self):
        assert validate_description("x" * 500) == []

    def test_501_chars_rejected(self):
        errors = validate_description("x" * 501)
        assert any(e["field"] == "description" for e in errors)

    def test_non_string_rejected(self):
        errors = validate_description(42)
        assert any(e["field"] == "description" for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# VAL-09: validate_host_not_private — SSRF prevention
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateHostNotPrivate:
    """VAL-09"""

    def test_public_ip_accepted(self):
        assert validate_host_not_private("8.8.8.8") == []

    def test_public_hostname_accepted(self):
        assert validate_host_not_private("my-db.example.com") == []

    def test_rfc1918_10_rejected(self):
        errors = validate_host_not_private("10.0.0.1")
        assert errors

    def test_rfc1918_172_rejected(self):
        errors = validate_host_not_private("172.16.0.1")
        assert errors

    def test_rfc1918_192_rejected(self):
        errors = validate_host_not_private("192.168.1.100")
        assert errors

    def test_loopback_127_rejected(self):
        errors = validate_host_not_private("127.0.0.1")
        assert errors

    def test_localhost_rejected(self):
        errors = validate_host_not_private("localhost")
        assert errors

    def test_local_tld_rejected(self):
        errors = validate_host_not_private("mydb.local")
        assert errors


# ─────────────────────────────────────────────────────────────────────────────
# VAL-10: validate_port
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatePort:
    """VAL-10"""

    def test_valid_port(self):
        assert validate_port(5432) == []

    def test_port_1(self):
        assert validate_port(1) == []

    def test_port_65535(self):
        assert validate_port(65535) == []

    def test_port_0_rejected(self):
        errors = validate_port(0)
        assert errors

    def test_port_65536_rejected(self):
        errors = validate_port(65536)
        assert errors

    def test_string_port_rejected(self):
        errors = validate_port("5432")
        assert errors

    def test_bool_rejected(self):
        errors = validate_port(True)
        assert errors


# ─────────────────────────────────────────────────────────────────────────────
# VAL-11: validate_credential_structure — postgresql
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatePostgresCredentials:
    """VAL-11"""

    def test_valid_postgresql_credentials(self):
        errors = validate_credential_structure(
            "postgresql",
            {
                "host": "db.example.com",
                "port": 5432,
                "database": "mydb",
                "username": "user",
                "password": "s3cr3t",
            },
        )
        assert errors == []

    def test_missing_password_rejected(self):
        errors = validate_credential_structure(
            "postgresql",
            {
                "host": "db.example.com",
                "port": 5432,
                "database": "mydb",
                "username": "user",
            },
        )
        assert any(e["field"] == "credentials.password" for e in errors)

    def test_private_host_rejected(self):
        from unittest.mock import patch

        with patch("app.services.data_sources.validation.settings") as mock_settings:
            mock_settings.DEBUG = False
            errors = validate_credential_structure(
                "postgresql",
                {
                    "host": "10.0.0.5",
                    "port": 5432,
                    "database": "mydb",
                    "username": "user",
                    "password": "secret",
                },
            )
        assert any("host" in e["field"] for e in errors)

    def test_agent_mode_skips_validation(self):
        errors = validate_credential_structure(
            "postgresql",
            {},
            connection_mode="agent",
        )
        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# VAL-12: validate_credential_structure — bigquery
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateBigqueryCredentials:
    """VAL-12"""

    def _valid_sa_json(self):
        import json

        sa = {k: "value" for k in BIGQUERY_SERVICE_ACCOUNT_REQUIRED_KEYS}
        return json.dumps(sa)

    def test_valid_bigquery_credentials(self):
        errors = validate_credential_structure(
            "bigquery",
            {"service_account_json": self._valid_sa_json()},
        )
        assert errors == []

    def test_missing_service_account_json(self):
        errors = validate_credential_structure("bigquery", {})
        assert any("service_account_json" in e["field"] for e in errors)

    def test_invalid_json_rejected(self):
        errors = validate_credential_structure(
            "bigquery",
            {"service_account_json": "{not valid json"},
        )
        assert errors

    def test_missing_required_key_rejected(self):
        import json

        sa = {k: "v" for k in BIGQUERY_SERVICE_ACCOUNT_REQUIRED_KEYS}
        del sa["private_key"]
        errors = validate_credential_structure(
            "bigquery",
            {"service_account_json": json.dumps(sa)},
        )
        assert errors


# ─────────────────────────────────────────────────────────────────────────────
# VAL-13: validate_immutable_fields_not_changed
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateImmutableFields:
    """VAL-13"""

    def test_changing_source_type_rejected(self):
        errors = validate_immutable_fields_not_changed({"source_type": "mysql"})
        assert any(e["field"] == "source_type" for e in errors)

    def test_other_fields_ok(self):
        errors = validate_immutable_fields_not_changed({"source_name": "new-name"})
        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# VAL-14: validate_create_payload — composite
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateCreatePayload:
    """VAL-14"""

    def _valid_payload(self):
        return {
            "source_name": "Prod PG",
            "source_type": "postgresql",
            "connection_mode": "direct",
            "environment": "production",
            "credentials": {
                "host": "db.example.com",
                "port": 5432,
                "database": "mydb",
                "username": "admin",
                "password": "secret",
            },
        }

    def test_valid_payload_passes(self):
        result = validate_create_payload(self._valid_payload())
        assert result.is_valid

    def test_multiple_errors_accumulated(self):
        result = validate_create_payload(
            {
                "source_name": "",
                "source_type": "invalid",
                "connection_mode": "bad",
                "environment": "bad",
                "credentials": {},
            }
        )
        assert not result.is_valid
        # Multiple distinct fields should have errors
        fields_with_errors = {e["field"] for e in result.errors}
        assert len(fields_with_errors) >= 3
