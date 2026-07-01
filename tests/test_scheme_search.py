"""Tests for profile/query based scheme candidate search."""

from app.models import CitizenProfile
from app.scheme_search import search_schemes_for_profile


def test_search_finds_pragati_for_full_matching_profile(full_pragati_profile: CitizenProfile) -> None:
    results = search_schemes_for_profile(full_pragati_profile)

    assert len(results) >= 1
    assert results[0].scheme.scheme_id == "aicte_pragati_degree"
    assert results[0].score >= 0.8


def test_search_returns_no_results_for_non_student() -> None:
    profile = CitizenProfile(
        age=35,
        state="Maharashtra",
        is_student=False,
    )

    results = search_schemes_for_profile(profile)

    assert results == []


def test_search_uses_disability_query_intent_for_partial_profile() -> None:
    # Query text matters when profile details are still sparse.
    profile = CitizenProfile(is_student=True)

    results = search_schemes_for_profile(
        profile,
        query_text="I need a scholarship for specially-abled students with disability.",
    )

    assert len(results) >= 1
    assert results[0].scheme.scheme_id == "aicte_saksham_degree"


def test_search_uses_girl_student_query_intent_for_partial_profile() -> None:
    profile = CitizenProfile(is_student=True)

    results = search_schemes_for_profile(
        profile,
        query_text="I need Pragati or girls scholarship information for my daughter.",
    )

    assert len(results) >= 1
    assert results[0].scheme.scheme_id == "aicte_pragati_degree"


def test_search_treats_b_tech_with_space_as_technical_course() -> None:
    # Guards the user-reported bug where "B Tech" was not recognized as a
    # technical course.
    profile = CitizenProfile(
        is_student=True,
        education_level="undergraduate",
        course_name="B Tech",
    )

    results = search_schemes_for_profile(
        profile,
        query_text="I need scholarship help for disability.",
    )

    assert len(results) >= 1
    assert any(
        "technical" in reason.lower()
        for reason in results[0].matched_reasons
    )
