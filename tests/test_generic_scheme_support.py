"""Tests proving new JSON-defined schemes work without Python branches."""

import os

# Settings are loaded at import time by app modules; this avoids requiring a
# real Groq key for deterministic unit tests.
os.environ.setdefault("GROQ_API_KEY", "test-key")

from app.eligibility_checker import check_eligibility_for_scheme
from app.models import (
    CitizenProfile,
    EligibilityRule,
    GovernmentLevel,
    RuleFailureType,
    RuleOperator,
    Scheme,
    SchemeCategory,
    SourceType,
)
from app.ranking import rank_scheme_results
from app.scheme_search import search_schemes_for_profile
from app.taor_agent import SevaSathiTAORAgent


def _test_source() -> dict:
    """Return the minimum valid source metadata for test-only schemes."""
    return {
        "source_type": SourceType.verified_manual_entry,
        "title": "Test source",
        "publisher": "Test Publisher",
        "url": "https://example.gov.in/test",
        "last_checked_at": "2026-06-27",
        "notes": None,
    }


def _senior_income_support_scheme() -> Scheme:
    """Build a synthetic scheme that is checked entirely by eligibility_rules."""
    return Scheme(
        scheme_id="test_senior_income_support",
        name="Test Senior Income Support",
        category=SchemeCategory.financial_assistance,
        government_level=GovernmentLevel.state,
        state="Maharashtra",
        summary="Financial assistance for senior citizens from low-income households.",
        target_groups=["senior citizens", "low-income households"],
        benefits=["Monthly income support."],
        required_documents=["Age proof", "Income proof"],
        eligibility_text=[
            "Applicant should be at least 60 years old.",
            "Annual family income should be at or below Rs. 3 lakh.",
        ],
        eligibility_rules=[
            EligibilityRule(
                field_name="age",
                operator=RuleOperator.min_value,
                min_value=60,
                matched_reason="The applicant meets the minimum age requirement.",
                missing_message="Applicant age detail is required.",
                failed_reason="Applicant is below the minimum age requirement.",
                failure_type=RuleFailureType.blocking,
            ),
            EligibilityRule(
                field_name="annual_family_income",
                operator=RuleOperator.max_value,
                max_value=300000,
                matched_reason="The applicant is within the income limit.",
                missing_message="Applicant income detail is required.",
                failed_reason="Applicant is above the income limit.",
                failure_type=RuleFailureType.blocking,
            ),
        ],
        application_steps=["Apply through the official test portal."],
        application_window=None,
        official_apply_url="https://example.gov.in/apply",
        sources=[_test_source()],
    )


def _minority_grant_scheme() -> Scheme:
    """Build a synthetic scheme used to verify generic follow-up generation."""
    return Scheme(
        scheme_id="test_minority_grant",
        name="Test Minority Community Grant",
        category=SchemeCategory.financial_assistance,
        government_level=GovernmentLevel.central,
        state=None,
        summary="Financial assistance for applicants from minority communities.",
        target_groups=["minority community applicants"],
        benefits=["One-time grant support."],
        required_documents=["Community declaration"],
        eligibility_text=["Applicant should belong to a minority community."],
        eligibility_rules=[
            EligibilityRule(
                field_name="minority_status",
                operator=RuleOperator.is_true,
                matched_reason="The applicant belongs to a minority community.",
                missing_message="This detail is needed before checking.",
                failed_reason="Applicant does not meet the community condition.",
                failure_type=RuleFailureType.blocking,
            ),
        ],
        application_steps=["Apply through the official test portal."],
        application_window=None,
        official_apply_url="https://example.gov.in/minority-apply",
        sources=[_test_source()],
    )


def test_rule_driven_search_supports_new_scheme_without_code_branch() -> None:
    # This is the main scalability guarantee: adding a scheme with JSON rules
    # should not require editing eligibility_checker.py or taor_agent.py.
    scheme = _senior_income_support_scheme()
    profile = CitizenProfile(
        age=67,
        state="Maharashtra",
        annual_family_income=200000,
    )

    results = search_schemes_for_profile(
        profile,
        schemes=[scheme],
        query_text="senior income support",
    )

    assert len(results) == 1
    assert results[0].scheme.scheme_id == "test_senior_income_support"
    assert results[0].score >= 0.9
    assert "The applicant meets the minimum age requirement." in results[0].matched_reasons


def test_rule_driven_search_blocks_new_scheme_when_rule_fails() -> None:
    scheme = _senior_income_support_scheme()
    profile = CitizenProfile(
        age=45,
        state="Maharashtra",
        annual_family_income=200000,
    )

    results = search_schemes_for_profile(
        profile,
        schemes=[scheme],
        query_text="senior income support",
    )

    assert results == []


def test_follow_up_question_comes_from_rule_field_not_scheme_specific_text() -> None:
    # The follow-up generator should read rule field names, so unseen future
    # schemes can still ask sensible questions.
    scheme = _minority_grant_scheme()
    profile = CitizenProfile()
    search_results = search_schemes_for_profile(
        profile,
        schemes=[scheme],
        query_text="minority community grant assistance",
    )
    eligibility_results = [
        check_eligibility_for_scheme(profile, search_result.scheme)
        for search_result in search_results
    ]
    ranked_results = rank_scheme_results(
        search_results=search_results,
        eligibility_results=eligibility_results,
    )

    questions = SevaSathiTAORAgent()._build_follow_up_questions(ranked_results)

    assert questions == [
        "Do you belong to a minority community? You may answer Yes, No, or Prefer not to say."
    ]
