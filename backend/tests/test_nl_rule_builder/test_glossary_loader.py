import uuid
from unittest.mock import MagicMock

import pytest
from app.schemas.glossary import GlossaryListResponse, GlossaryTermResponse
from app.services.nl_rule_builder.glossary_loader import GlossaryPromptTerm, GlossaryTermLoader

WORKSPACE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _term(
    name: str,
    technical_name: str | None = None,
    synonyms: list[str] | None = None,
    definition: str | None = None,
    domain: str | None = None,
):
    return GlossaryTermResponse(
        term_id=uuid.uuid4(),
        workspace_id=WORKSPACE_ID,
        business_name=name,
        technical_name=technical_name,
        definition=definition,
        synonyms=synonyms or [],
        domain=domain,
        linked_asset_ids=[],
    )


class TestGlossaryLoader:
    def test_empty_rule_text_returns_empty_list(self):
        glossary_service = MagicMock()
        loader = GlossaryTermLoader(glossary_service=glossary_service)

        assert (
            loader.load_glossary_for_rule(MagicMock(), WORKSPACE_ID, "   ", tenant_id=TENANT_ID)
            == []
        )
        glossary_service.list_terms_for_tenant.assert_not_called()

    def test_empty_workspace_glossary_returns_empty(self):
        glossary_service = MagicMock()
        glossary_service.list_terms_for_tenant.return_value = GlossaryListResponse(
            items=[], total=0, page=1, page_size=20
        )
        loader = GlossaryTermLoader(glossary_service=glossary_service)

        result = loader.load_glossary_for_rule(
            MagicMock(), WORKSPACE_ID, "check completeness of email", tenant_id=TENANT_ID
        )

        assert result == []
        glossary_service.list_terms_for_tenant.assert_called_once()

    def test_relevance_prefers_business_name_and_synonyms(self):
        term_email = _term(
            name="Employee Email Address",
            technical_name="employee_email",
            synonyms=["email", "emp email"],
            definition="Email address of the employee",
        )
        term_phone = _term(
            name="Customer Phone",
            technical_name="customer_phone",
            synonyms=["phone number"],
            definition="Primary customer phone",
        )

        glossary_service = MagicMock()
        glossary_service.list_terms_for_tenant.return_value = GlossaryListResponse(
            items=[term_phone, term_email],
            total=2,
            page=1,
            page_size=20,
        )
        loader = GlossaryTermLoader(glossary_service=glossary_service)

        result = loader.load_glossary_for_rule(
            MagicMock(), WORKSPACE_ID, "check completeness of employee email", tenant_id=TENANT_ID
        )

        # Unrelated terms can be filtered out when relevance score is zero.
        assert len(result) == 1
        assert result[0].business_name == "Employee Email Address"
        assert result[0].relevance_score > 0

    def test_load_filters_out_zero_score_terms(self):
        term = _term(name="Supplier IBAN", synonyms=["iban"], definition="Bank account")
        glossary_service = MagicMock()
        glossary_service.list_terms_for_tenant.return_value = GlossaryListResponse(
            items=[term], total=1, page=1, page_size=20
        )
        loader = GlossaryTermLoader(glossary_service=glossary_service)

        result = loader.load_glossary_for_rule(
            MagicMock(), WORKSPACE_ID, "customer birth date in future", tenant_id=TENANT_ID
        )

        assert result == []

    def test_caps_result_count_to_max_terms(self):
        terms = [
            _term(name=f"Email Concept {i}", synonyms=["email"], definition="email value")
            for i in range(25)
        ]
        glossary_service = MagicMock()
        glossary_service.list_terms_for_tenant.return_value = GlossaryListResponse(
            items=terms, total=25, page=1, page_size=200
        )
        loader = GlossaryTermLoader(glossary_service=glossary_service)

        result = loader.load_glossary_for_rule(
            MagicMock(), WORKSPACE_ID, "email must not be empty", max_terms=20, tenant_id=TENANT_ID
        )

        assert len(result) == 20

    def test_graceful_fallback_on_service_error(self):
        glossary_service = MagicMock()
        glossary_service.list_terms_for_tenant.side_effect = RuntimeError("db down")
        loader = GlossaryTermLoader(glossary_service=glossary_service)

        result = loader.load_glossary_for_rule(
            MagicMock(), WORKSPACE_ID, "email not null", tenant_id=TENANT_ID
        )

        assert result == []

    def test_compute_score_supports_partial_token_matching(self):
        loader = GlossaryTermLoader(glossary_service=MagicMock())
        term = _term(
            name="Employee Email Address",
            technical_name="emp_email_addr",
            synonyms=["employee_mail"],
            definition="corporate employee email",
        )

        score = loader._compute_term_relevance_score(term, "emp email must be complete")

        assert score > 0.0

    def test_prompt_format_includes_core_fields(self):
        loader = GlossaryTermLoader(glossary_service=MagicMock())
        terms = [
            GlossaryPromptTerm(
                term_id=uuid.uuid4(),
                business_name="Employee Email Address",
                technical_name="employee_email",
                synonyms=["email"],
                definition="Official employee email",
                data_type="string",
                domain="HR",
                linked_asset_ids=["dataset:hr_employees", "column:email_address"],
                relevance_score=0.92,
            )
        ]

        section = loader.format_glossary_for_prompt(terms)

        assert "BUSINESS GLOSSARY" in section
        assert "Employee Email Address" in section
        assert "dataset:hr_employees" in section

    def test_prompt_format_respects_max_chars(self):
        loader = GlossaryTermLoader(glossary_service=MagicMock())
        terms = [
            GlossaryPromptTerm(
                term_id=uuid.uuid4(),
                business_name=f"Very Long Term {i}",
                technical_name="x" * 40,
                synonyms=["x" * 40, "y" * 40],
                definition="z" * 200,
                data_type="string",
                domain="finance",
                linked_asset_ids=["dataset:very_long_dataset_name"],
                relevance_score=0.7,
            )
            for i in range(10)
        ]

        section = loader.format_glossary_for_prompt(terms, max_chars=400)

        assert len(section) <= 400
        assert "BUSINESS GLOSSARY" in section


@pytest.mark.parametrize(
    "left,right,expected_min",
    [
        ({"email", "employee"}, {"employee", "email"}, 1.0),
        ({"emp", "email"}, {"employee", "email"}, 0.3),
        ({"iban"}, {"phone"}, 0.0),
    ],
)
def test_token_overlap(left, right, expected_min):
    score = GlossaryTermLoader._token_overlap(left, right)
    assert score >= expected_min
