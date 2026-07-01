"""Candidate scheme search and relevance scoring.

Search is intentionally lighter than final eligibility. It estimates which
schemes are worth checking by combining state fit, machine-readable eligibility
rule matches, and query/scheme text overlap.
"""

from app.models import (
    ApplicationStatus,
    CitizenProfile,
    RuleFailureType,
    Scheme,
    SchemeSearchResult,
)

import re
from typing import Optional, List

from app.rule_engine import rule_passes, value_is_missing
from app.scheme_loader import load_schemes


QUERY_STOP_WORDS = {
    # Common words that make text overlap noisy and should not affect ranking.
    "about",
    "also",
    "and",
    "any",
    "apply",
    "are",
    "can",
    "for",
    "from",
    "give",
    "help",
    "how",
    "need",
    "scheme",
    "schemes",
    "scholarship",
    "scholarships",
    "student",
    "students",
    "tell",
    "the",
    "what",
    "which",
    "with",
}


def _normalize_text(value: Optional[str]) -> str:
    """Normalize optional text for case-insensitive comparisons."""
    if value is None:
        return ""
    
    return value.strip().lower()


def _tokenize_text(value: str) -> set[str]:
    """Tokenize text into meaningful search terms for query overlap scoring."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(value))
        if len(token) > 2 and token not in QUERY_STOP_WORDS
    }



def _build_scheme_text(scheme: Scheme) -> str:
    """Flatten searchable scheme fields into one lower-case text blob."""
    parts: list[str] = [
        scheme.name,
        scheme.summary,
        scheme.category.value,
        scheme.government_level.value
    ]

    parts.extend(scheme.target_groups)
    parts.extend(scheme.benefits)
    parts.extend(scheme.required_documents)
    parts.extend(scheme.eligibility_text)

    return " ".join(parts).lower()



def _is_student_focused_scheme(scheme_text: str) -> bool:
    """Best-effort fallback detector for schemes without eligibility rules."""
    student_terms = ["student", "scholarship", "education", "course", "institution"]
    return any(term in scheme_text for term in student_terms)


def _is_technical_degree_scheme(scheme_text: str) -> bool:
    """Best-effort fallback detector for technical-course scheme text."""
    technical_terms = ["technical", "degree", "aicte", "engineering"]
    return any(term in scheme_text for term in technical_terms)


def _course_looks_technical(course_name: Optional[str]) -> bool:
    """Recognize common technical course spellings such as B Tech/B.Tech/BTech."""
    normalized_course = _normalize_text(course_name)
    compact_course = re.sub(r"[^a-z0-9]+", "", normalized_course)

    return (
        any(
            term in normalized_course
            for term in ["b.tech", "b.e", "engineering", "technology"]
        )
        or "btech" in compact_course
        or compact_course.startswith("be")
    )


def _score_scheme_for_query(
    query_text: Optional[str],
    scheme_text: str,
) -> tuple[float, list[str]]:
    """Score lexical overlap between the original user query and scheme text."""
    if not query_text:
        return 0.0, []

    score = 0.0
    matched_reasons: list[str] = []
    query_tokens = _tokenize_text(query_text)

    if query_tokens:
        scheme_tokens = _tokenize_text(scheme_text)
        overlapping_terms = sorted(query_tokens & scheme_tokens)

        if overlapping_terms:
            score += min(len(overlapping_terms) * 0.02, 0.10)
            matched_reasons.append(
                "The user's query shares relevant terms with this scheme: "
                + ", ".join(overlapping_terms[:5])
                + "."
            )

    return score, matched_reasons


def _score_scheme_for_rules(
    profile: CitizenProfile,
    scheme: Scheme,
) -> tuple[float, list[str], list[str], bool]:
    """Score a scheme by checking available profile values against its rules.

    Returns:
        A tuple of `(score, matched_reasons, possible_concerns, is_blocked)`.
        `is_blocked` is true when a clear blocking rule failure means the
        scheme should not be considered a default candidate.
    """
    if not scheme.eligibility_rules:
        return 0.0, [], [], False

    score = 0.0
    matched_reasons: list[str] = []
    possible_concerns: list[str] = []
    # Rule score is capped so state/query/window signals can still contribute.
    score_per_rule = 0.70 / len(scheme.eligibility_rules)

    for rule in scheme.eligibility_rules:
        if not hasattr(profile, rule.field_name):
            possible_concerns.append(
                f"The scheme checks '{rule.field_name}', but that profile field is not available in the app yet."
            )
            continue

        profile_value = getattr(profile, rule.field_name)

        if value_is_missing(profile_value):
            possible_concerns.append(rule.missing_message)
            continue

        if rule_passes(profile_value=profile_value, rule=rule):
            score += score_per_rule
            matched_reasons.append(rule.matched_reason)
            continue

        if rule.failure_type == RuleFailureType.blocking:
            return (
                0.0,
                [],
                [rule.failed_reason],
                True,
            )

        possible_concerns.append(rule.failed_reason)

    return min(score, 0.70), matched_reasons, possible_concerns, False


def _score_scheme_with_text_fallback(
    profile: CitizenProfile,
    scheme_text: str,
) -> tuple[float, list[str], list[str], bool]:
    """Fallback scoring for schemes that do not yet have eligibility_rules."""
    score = 0.0
    matched_reasons: list[str] = []
    possible_concerns: list[str] = []

    is_student_focused = _is_student_focused_scheme(scheme_text)

    if is_student_focused and profile.is_student is False:
        return (
            0.0,
            [],
            ["This scheme appears student-focused, but the user is not currently a student."],
            True,
        )

    if is_student_focused and profile.is_student is True:
        score += 0.20
        matched_reasons.append("The user is a student and the scheme is student-focused.")
    elif is_student_focused and profile.is_student is None:
        possible_concerns.append("The scheme is student-focused, but student status is missing.")

    if "income" in scheme_text:
        if profile.annual_family_income is not None:
            score += 0.10
            matched_reasons.append("The user provided family income, which is needed for this scheme.")
        else:
            possible_concerns.append("The scheme appears income-based, but family income is missing.")

    return score, matched_reasons, possible_concerns, False



def score_scheme_for_profile(
    profile: CitizenProfile,
    scheme: Scheme,
    query_text: Optional[str] = None,
) -> SchemeSearchResult:
    """Return one scored search result for a profile/scheme pair.

    Args:
        profile: Merged citizen profile available so far.
        scheme: Scheme loaded from the verified local database.
        query_text: Original user search intent, preserved across follow-ups.
    """
    score = 0.0
    matched_reasons: list[str] = []
    possible_concerns: list[str] = []

    scheme_text = _build_scheme_text(scheme)

    user_state = _normalize_text(profile.state)
    scheme_state = _normalize_text(scheme.state)

    if scheme_state and user_state and scheme_state != user_state:
        # State mismatch is a hard retrieval block when both values are known.
        return SchemeSearchResult(
            scheme=scheme,
            score=0.0,
            matched_reasons=[],
            possible_concerns=[
                f"This scheme is for {scheme.state}, but the user's state is {profile.state}."
            ],
        )

    if scheme.state is None:
        score += 0.20
        matched_reasons.append("The scheme is not limited to one state in our database.")
    elif user_state and scheme_state == user_state:
        score += 0.25
        matched_reasons.append(f"The scheme applies to the user's state: {profile.state}.")
    else:
        possible_concerns.append("User state is missing, so state-level relevance cannot be fully checked.")

    if scheme.eligibility_rules:
        rule_score, rule_reasons, rule_concerns, is_blocked = _score_scheme_for_rules(
            profile=profile,
            scheme=scheme,
        )

        if is_blocked:
            return SchemeSearchResult(
                scheme=scheme,
                score=0.0,
                matched_reasons=[],
                possible_concerns=rule_concerns,
            )

        score += rule_score
        matched_reasons.extend(rule_reasons)
        possible_concerns.extend(rule_concerns)
    else:
        fallback_score, fallback_reasons, fallback_concerns, is_blocked = _score_scheme_with_text_fallback(
            profile=profile,
            scheme_text=scheme_text,
        )

        if is_blocked:
            return SchemeSearchResult(
                scheme=scheme,
                score=0.0,
                matched_reasons=[],
                possible_concerns=fallback_concerns,
            )

        score += fallback_score
        matched_reasons.extend(fallback_reasons)
        possible_concerns.extend(fallback_concerns)

    if _is_technical_degree_scheme(scheme_text) and not scheme.eligibility_rules:
        course_name = _normalize_text(profile.course_name)

        if _course_looks_technical(course_name):
            score += 0.10
            matched_reasons.append("The user's course looks technical or engineering-related.")
        elif not course_name:
            possible_concerns.append("The scheme may require a technical course, but course name is missing.")

    if scheme.application_window and scheme.application_window.status == ApplicationStatus.open:
        score += 0.05
        matched_reasons.append("The scheme application window is marked open in our verified database.")

    query_score, query_reasons = _score_scheme_for_query(
        query_text=query_text,
        scheme_text=scheme_text,
    )
    score += query_score
    matched_reasons.extend(query_reasons)

    final_score = min(score, 1.0)

    return SchemeSearchResult(
        scheme=scheme,
        score=round(final_score, 2),
        matched_reasons=matched_reasons,
        possible_concerns=possible_concerns,
    )


def search_schemes_for_profile(
    profile: CitizenProfile,
    schemes: Optional[List[Scheme]] = None,
    min_score: float = 0.25,
    query_text: Optional[str] = None,
) -> list[SchemeSearchResult]:
    """Find and sort schemes relevant to the current profile.

    Args:
        profile: Current merged profile.
        schemes: Optional scheme list for tests; defaults to `data/schemes.json`.
        min_score: Minimum relevance score included in normal search results.
        query_text: Original user query used for text-overlap relevance.
    """
    if schemes is None:
        schemes = load_schemes()

    results = [
        score_scheme_for_profile(
            profile=profile,
            scheme=scheme,
            query_text=query_text,
        )
        for scheme in schemes
    ]

    filtered_results = [
        result
        for result in results
        if result.score >= min_score
    ]

    return sorted(filtered_results, key=lambda result: result.score, reverse=True)
