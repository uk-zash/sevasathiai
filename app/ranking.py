from typing import List

from app.models import (
    EligibilityResult,
    MatchStatus,
    RankedSchemeResult,
    RecommendationLabel,
    SchemeSearchResult,
)


def _base_score_for_status(status: MatchStatus) -> float:
    if status == MatchStatus.likely_match:
        return 1.0

    if status == MatchStatus.possible_match:
        return 0.65

    if status == MatchStatus.not_enough_information:
        return 0.35

    return 0.05


def _label_for_status(status: MatchStatus) -> RecommendationLabel:
    if status == MatchStatus.likely_match:
        return RecommendationLabel.strong_match

    if status == MatchStatus.possible_match:
        return RecommendationLabel.possible_match

    if status == MatchStatus.not_enough_information:
        return RecommendationLabel.needs_information

    return RecommendationLabel.not_recommended


def rank_scheme_results(
    search_results: List[SchemeSearchResult],
    eligibility_results: List[EligibilityResult],
) -> List[RankedSchemeResult]:
    
    eligibility_by_scheme_id = {
        result.scheme_id: result
        for result in eligibility_results
    }

    ranked_results: List[RankedSchemeResult] = []

    for search_result in search_results:
        scheme_id = search_result.scheme.scheme_id
        eligibility_result = eligibility_by_scheme_id.get(scheme_id)

        if eligibility_result is None:
            continue

        status_base_score = _base_score_for_status(eligibility_result.status)

        missing_penalty = min(
            len(eligibility_result.missing_information) * 0.04,
            0.20,
        )

        blocking_penalty = min(
            len(eligibility_result.not_matched_reasons) * 0.20,
            0.60,
        )

        rank_score = (
            status_base_score * 0.70
            + search_result.score * 0.30
            - missing_penalty
            - blocking_penalty
        )

        rank_score = max(0.0, min(rank_score, 1.0))

        rank_reasons: List[str] = [
            f"Eligibility status is {eligibility_result.status.value}.",
            f"Search relevance score is {search_result.score}.",
        ]

        if eligibility_result.not_matched_reasons:
            rank_reasons.append(
                f"{len(eligibility_result.not_matched_reasons)} blocking issue(s) found."
            )

        if eligibility_result.missing_information:
            rank_reasons.append(
                f"{len(eligibility_result.missing_information)} missing or uncertain detail(s) found."
            )

        if eligibility_result.matched_reasons:
            rank_reasons.append(
                f"{len(eligibility_result.matched_reasons)} check(s) matched."
            )

        ranked_results.append(
            RankedSchemeResult(
                search_result=search_result,
                eligibility_result=eligibility_result,
                rank_score=round(rank_score, 2),
                recommendation_label=_label_for_status(eligibility_result.status),
                rank_reasons=rank_reasons,
            )
        )

    return sorted(
        ranked_results,
        key=lambda result: result.rank_score,
        reverse=True,
    )