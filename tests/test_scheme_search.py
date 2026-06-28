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