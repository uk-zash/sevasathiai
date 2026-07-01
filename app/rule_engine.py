"""Generic eligibility-rule evaluator.

This module turns `EligibilityRule` objects from scheme JSON into executable
checks against `CitizenProfile`. New schemes should prefer eligibility_rules so
they can use this generic engine instead of scheme-specific Python code.
"""

import re
from typing import Any, Optional

from app.models import (
    ApplicationStatus,
    CitizenProfile,
    EligibilityResult,
    MatchStatus,
    RuleFailureType,
    RuleOperator,
    Scheme,
)

MISSING_SENTINELS = {
    "",
    "unknown",
    "prefer_not_to_say",
}


def _raw_value(value: Any) -> Any:
    """Return enum `.value` when present, otherwise return the value unchanged."""
    if hasattr(value, "value"):
        return value.value

    return value


def _is_missing(value: Any) -> bool:
    """Treat nulls, empty strings, and privacy/unknown sentinels as missing."""
    raw = _raw_value(value)

    if raw is None:
        return True

    if isinstance(raw, str) and raw.strip().lower() in MISSING_SENTINELS:
        return True

    return False


def _normalize_for_compare(value: Any) -> Any:
    """Normalize scalar values for equality/list comparisons."""
    raw = _raw_value(value)

    if isinstance(raw, str):
        return raw.strip().lower()

    return raw


def _normalize_for_contains(value: Any) -> str:
    """Normalize text for loose substring matching."""
    normalized = str(_normalize_for_compare(value))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def _compact_for_contains(value: Any) -> str:
    """Remove punctuation/spaces so `B Tech`, `B.Tech`, and `BTech` match."""
    return re.sub(r"[^a-z0-9]+", "", str(_normalize_for_compare(value)))


# FIX: Changed 'float | None' to 'Optional[float]' for Python 3.9 compatibility
def _to_float(value: Any) -> Optional[float]:
    """Convert profile values to floats for numeric min/max rules."""
    raw = _raw_value(value)

    if raw is None:
        return None

    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _rule_passes(profile_value: Any, rule) -> bool:
    """Return whether one profile value satisfies one EligibilityRule."""
    operator = rule.operator

    if operator == RuleOperator.equals:
        return _normalize_for_compare(profile_value) == _normalize_for_compare(rule.expected_value)

    if operator == RuleOperator.in_list:
        normalized_value = _normalize_for_compare(profile_value)
        normalized_expected_values = [
            _normalize_for_compare(value) for value in rule.expected_values
        ]

        return normalized_value in normalized_expected_values

    if operator == RuleOperator.max_value:
        numeric_value = _to_float(profile_value)

        if numeric_value is None or rule.max_value is None:
            return False

        return numeric_value <= rule.max_value

    if operator == RuleOperator.min_value:
        numeric_value = _to_float(profile_value)

        if numeric_value is None or rule.min_value is None:
            return False

        return numeric_value >= rule.min_value

    if operator == RuleOperator.contains_any:
        normalized_value = _normalize_for_contains(profile_value)
        compact_value = _compact_for_contains(profile_value)
        search_terms = [
            _normalize_for_contains(value) for value in rule.expected_values
        ]
        compact_search_terms = [
            _compact_for_contains(value) for value in rule.expected_values
        ]

        return any(term in normalized_value for term in search_terms) or any(
            term and term in compact_value
            for term in compact_search_terms
        )

    if operator == RuleOperator.is_true:
        return profile_value is True

    if operator == RuleOperator.is_false:
        return profile_value is False

    raise ValueError(f"Unsupported rule operator: {operator}")


def value_is_missing(value: Any) -> bool:
    """Public wrapper used by search scoring to share missing-value semantics."""
    return _is_missing(value)


def rule_passes(profile_value: Any, rule) -> bool:
    """Public wrapper used by search scoring to share rule-pass semantics."""
    return _rule_passes(profile_value=profile_value, rule=rule)


def _build_generic_user_message(
    scheme: Scheme,
    status: MatchStatus,
) -> str:
    """Create a plain-language message for a generic eligibility result."""
    if status == MatchStatus.likely_match:
        return (
            f"You appear to match the main readiness checks for {scheme.name} based on the information provided. "
            "This is not final eligibility. Please verify all details and apply only through the official portal."
        )

    if status == MatchStatus.possible_match:
        return (
            f"You may match {scheme.name}, but some important details are still missing or uncertain. "
            "Please answer the follow-up questions and verify details on the official portal."
        )

    if status == MatchStatus.not_enough_information:
        return (
            f"I do not have enough information to assess {scheme.name} yet. "
            "Please provide the missing details and verify everything on the official portal."
        )

    return (
        f"Based on the information provided, you do not appear to match {scheme.name}. "
        "Please verify on the official portal because scheme rules and user details can vary."
    )


def _decide_generic_result(
    scheme: Scheme,
    matched_reasons: list[str],
    missing_information: list[str],
    not_matched_reasons: list[str],
) -> EligibilityResult:
    """Convert collected rule outcomes into a final EligibilityResult."""
    if not_matched_reasons:
        status = MatchStatus.not_a_match
        confidence = 0.8
    elif missing_information:
        if len(matched_reasons) >= 3:
            status = MatchStatus.possible_match
            confidence = 0.6
        else:
            status = MatchStatus.not_enough_information
            confidence = 0.35
    else:
        status = MatchStatus.likely_match
        confidence = 0.85

    return EligibilityResult(
        scheme_id=scheme.scheme_id,
        status=status,
        confidence=confidence,
        matched_reasons=matched_reasons,
        missing_information=missing_information,
        not_matched_reasons=not_matched_reasons,
        user_message=_build_generic_user_message(
            scheme=scheme,
            status=status,
        ),
    )


def check_scheme_with_rules(
    profile: CitizenProfile,
    scheme: Scheme,
) -> EligibilityResult:
    """Evaluate all machine-readable rules for one scheme and profile.

    Args:
        profile: Current merged user profile.
        scheme: Scheme whose `eligibility_rules` should be checked.

    Returns:
        EligibilityResult with matched, missing, and blocking details.
    """
    if not scheme.eligibility_rules:
        return EligibilityResult(
            scheme_id=scheme.scheme_id,
            status=MatchStatus.not_enough_information,
            confidence=0.2,
            matched_reasons=[],
            missing_information=[
                "This scheme does not yet have machine-readable eligibility rules."
            ],
            not_matched_reasons=[],
            user_message=(
                "This scheme exists in the verified database, but machine-readable "
                "eligibility rules have not been added yet. Please verify on the official portal."
            ),
        )

    matched_reasons: list[str] = []
    missing_information: list[str] = []
    not_matched_reasons: list[str] = []

    for rule in scheme.eligibility_rules:
        # Invalid field names are data/config issues, so they are surfaced as
        # missing information instead of crashing the user flow.
        if not hasattr(profile, rule.field_name):
            missing_information.append(
                f"Internal rule configuration error: profile field '{rule.field_name}' does not exist."
            )
            continue

        profile_value = getattr(profile, rule.field_name)

        if _is_missing(profile_value):
            missing_information.append(rule.missing_message)
            continue

        if _rule_passes(profile_value=profile_value, rule=rule):
            matched_reasons.append(rule.matched_reason)
            continue

        if rule.failure_type == RuleFailureType.blocking:
            not_matched_reasons.append(rule.failed_reason)
        else:
            missing_information.append(rule.failed_reason)

    if scheme.application_window and scheme.application_window.status == ApplicationStatus.open:
        matched_reasons.append("The application window is marked open in the verified scheme database.")
    elif scheme.application_window and scheme.application_window.status == ApplicationStatus.closed:
        not_matched_reasons.append("The application window is marked closed in the verified scheme database.")
    else:
        missing_information.append("Current application window status is unknown.")

    return _decide_generic_result(
        scheme=scheme,
        matched_reasons=matched_reasons,
        missing_information=missing_information,
        not_matched_reasons=not_matched_reasons,
    )
