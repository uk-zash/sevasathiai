"""Regression tests for TAOR follow-up behavior and no-match messaging."""

import os

# Tests import settings-backed modules, so provide a harmless key before import.
os.environ.setdefault("GROQ_API_KEY", "test-key")

from app.eligibility_checker import check_eligibility_for_scheme
from app.models import AdmissionType, CitizenProfile, EducationLevel
from app.ranking import rank_scheme_results
from app.scheme_search import search_schemes_for_profile
from app.taor_agent import SevaSathiTAORAgent


def _ranked_results_for_profile(profile: CitizenProfile, query_text: str):
    """Run search, eligibility, and ranking without invoking the LLM extractor."""
    search_results = search_schemes_for_profile(
        profile,
        query_text=query_text,
    )
    eligibility_results = [
        check_eligibility_for_scheme(profile, search_result.scheme)
        for search_result in search_results
    ]

    return rank_scheme_results(
        search_results=search_results,
        eligibility_results=eligibility_results,
    )


def test_disability_query_asks_disability_status_before_girl_questions() -> None:
    # Protects the flow where disability intent should ask disability details
    # first, instead of jumping to girl-student questions.
    profile = CitizenProfile(
        is_student=True,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        receiving_other_scholarship=False,
    )
    ranked_results = _ranked_results_for_profile(
        profile=profile,
        query_text="I need a scholarship for specially-abled students with disability.",
    )

    questions = SevaSathiTAORAgent()._build_follow_up_questions(ranked_results)

    assert questions[0] == (
        "Does the specially-abled or disability condition apply to you for this scheme? "
        "You may answer Yes, No, or Prefer not to say."
    )


def test_disability_percentage_is_asked_after_disability_status_is_known() -> None:
    profile = CitizenProfile(
        is_student=True,
        has_disability=True,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        receiving_other_scholarship=False,
    )
    ranked_results = _ranked_results_for_profile(
        profile=profile,
        query_text="I need a scholarship for specially-abled students with disability.",
    )

    questions = SevaSathiTAORAgent()._build_follow_up_questions(ranked_results)

    assert questions[0] == (
        "What is your disability percentage as mentioned on your disability certificate? "
        "You may skip this if you are not comfortable sharing."
    )


def test_girl_student_match_still_asks_about_possible_disability_scheme() -> None:
    # A girl-student profile can still be eligible for disability schemes, so
    # matching Pragati must not suppress Saksham follow-up questions.
    profile = CitizenProfile(
        is_student=True,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=200000,
        has_valid_income_certificate=True,
        girl_children_in_family=1,
        receiving_other_scholarship=False,
        gender="female",
    )
    ranked_results = _ranked_results_for_profile(
        profile=profile,
        query_text="I need scholarship help for a girl student.",
    )

    questions = SevaSathiTAORAgent()._build_follow_up_questions(ranked_results)

    assert (
        "Does the specially-abled or disability condition apply to you for this scheme? "
        "You may answer Yes, No, or Prefer not to say."
    ) in questions


def test_follow_up_message_does_not_show_scheme_analysis() -> None:
    # During follow-up, the UI should ask for missing details instead of showing
    # premature ranking/eligibility analysis.
    message = SevaSathiTAORAgent()._build_follow_up_message(
        follow_up_questions=["Are you currently a student?"],
        privacy_warnings=[],
    )

    assert "I need a little more information" in message
    assert "AICTE" not in message
    assert "Recommendation" not in message
    assert "ranking" not in message.lower()


def test_all_blocked_results_are_not_actionable() -> None:
    # When every candidate has blocking failures, the user should see a no-match
    # message rather than a named scheme recommendation.
    profile = CitizenProfile(
        is_student=True,
        education_level=EducationLevel.undergraduate,
        course_name="BA",
        admission_type=AdmissionType.continuing_student,
        annual_family_income=900000,
        has_disability=False,
        gender="male",
    )
    ranked_results = _ranked_results_for_profile(
        profile=profile,
        query_text="I need scholarship help.",
    )

    agent = SevaSathiTAORAgent()
    actionable_results = agent._actionable_ranked_results(ranked_results)
    message = agent._build_no_verified_match_message(privacy_warnings=[])

    assert actionable_results == []
    assert "could not find a verified scheme match" in message
    assert "AICTE" not in message
