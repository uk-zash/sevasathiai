"""Tests for scheme eligibility decisions."""

from app.eligibility_checker import check_eligibility_for_scheme
from app.models import CitizenProfile, MatchStatus
from app.scheme_loader import load_schemes


def _get_pragati_scheme():
    """Load the Pragati scheme from the real curated test database."""
    schemes = load_schemes()

    for scheme in schemes:
        if scheme.scheme_id == "aicte_pragati_degree":
            return scheme

    raise AssertionError("AICTE Pragati scheme not found in test database.")


def test_pragati_checker_returns_likely_match_for_complete_profile(
    full_pragati_profile: CitizenProfile,
) -> None:
    scheme = _get_pragati_scheme()

    result = check_eligibility_for_scheme(
        profile=full_pragati_profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.likely_match
    assert result.confidence >= 0.8
    assert result.not_matched_reasons == []
    assert result.missing_information == []


def test_pragati_checker_blocks_income_above_limit(
    full_pragati_profile: CitizenProfile,
) -> None:
    scheme = _get_pragati_scheme()

    high_income_profile = full_pragati_profile.model_copy(
        update={"annual_family_income": 900000}
    )

    result = check_eligibility_for_scheme(
        profile=high_income_profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.not_a_match
    assert any(
        "above the Rs. 8 lakh annual limit" in reason
        for reason in result.not_matched_reasons
    )


def test_pragati_checker_asks_for_missing_aicte_status(
    full_pragati_profile: CitizenProfile,
) -> None:
    scheme = _get_pragati_scheme()

    missing_aicte_profile = full_pragati_profile.model_copy(
        update={"is_aicte_approved_institution": None}
    )

    result = check_eligibility_for_scheme(
        profile=missing_aicte_profile,
        scheme=scheme,
    )

    assert result.status == MatchStatus.possible_match
    assert any(
        "AICTE approval status" in item
        for item in result.missing_information
    )
