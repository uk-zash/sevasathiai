"""Tests for the generic JSON-rule eligibility engine."""

from app.models import (
    AdmissionType,
    CitizenProfile,
    EducationLevel,
    MatchStatus,
)
from app.scheme_loader import load_schemes
from app.rule_engine import check_scheme_with_rules


def _get_scheme(scheme_id: str):
    """Load one scheme by ID from data/schemes.json for rule-engine tests."""
    schemes = load_schemes()

    for scheme in schemes:
        if scheme.scheme_id == scheme_id:
            return scheme

    raise AssertionError(f"Scheme not found: {scheme_id}")


def test_generic_rule_engine_checks_saksham_likely_match() -> None:
    scheme = _get_scheme("aicte_saksham_degree")

    profile = CitizenProfile(
        age=20,
        state="Maharashtra",
        is_student=True,
        has_disability=True,
        disability_percentage=45,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        receiving_other_scholarship=False,
    )

    result = check_scheme_with_rules(
        profile=profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.likely_match
    assert result.not_matched_reasons == []
    assert result.missing_information == []


def test_generic_rule_engine_accepts_b_tech_with_space() -> None:
    scheme = _get_scheme("aicte_saksham_degree")

    profile = CitizenProfile(
        age=20,
        state="Maharashtra",
        is_student=True,
        has_disability=True,
        disability_percentage=45,
        education_level=EducationLevel.undergraduate,
        course_name="B Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        receiving_other_scholarship=False,
    )

    result = check_scheme_with_rules(
        profile=profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.likely_match
    assert not any(
        "course name does not appear" in reason.lower()
        for reason in result.not_matched_reasons
    )


def test_generic_rule_engine_blocks_saksham_disability_below_40() -> None:
    scheme = _get_scheme("aicte_saksham_degree")

    profile = CitizenProfile(
        age=20,
        state="Maharashtra",
        is_student=True,
        has_disability=True,
        disability_percentage=30,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        receiving_other_scholarship=False,
    )

    result = check_scheme_with_rules(
        profile=profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.not_a_match
    assert any(
        "not less than 40%" in reason
        for reason in result.not_matched_reasons
    )


def test_generic_rule_engine_asks_for_missing_disability_percentage() -> None:
    scheme = _get_scheme("aicte_saksham_degree")

    profile = CitizenProfile(
        age=20,
        state="Maharashtra",
        is_student=True,
        has_disability=True,
        disability_percentage=None,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        receiving_other_scholarship=False,
    )

    result = check_scheme_with_rules(
        profile=profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.possible_match
    assert any(
        "Disability percentage is missing" in item
        for item in result.missing_information
    )
