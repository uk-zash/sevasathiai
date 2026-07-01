"""Tests for Markdown/JSON report generation."""

from pathlib import Path

from app.eligibility_checker import check_eligibility_for_scheme
from app.models import AgentRunResult, CitizenProfile, MatchStatus
from app.output_writer import build_markdown_report, save_agent_outputs
from app.scheme_search import search_schemes_for_profile


def test_report_uses_blocking_issue_wording_for_not_a_match(
    full_pragati_profile: CitizenProfile,
) -> None:
    # A blocked scheme should explain issues clearly without listing documents
    # that are only useful for actionable matches.
    high_income_profile = full_pragati_profile.model_copy(
        update={"annual_family_income": 900000}
    )

    search_results = search_schemes_for_profile(
        high_income_profile,
        min_score=0,
    )
    eligibility = check_eligibility_for_scheme(
        profile=high_income_profile,
        scheme=search_results[0].scheme,
    )

    result = AgentRunResult(
        profile=high_income_profile,
        search_results=search_results,
        eligibility_results=[eligibility],
        steps=[],
        needs_follow_up=False,
        follow_up_questions=[],
        final_message=eligibility.user_message,
    )

    report = build_markdown_report(result)

    assert eligibility.status == MatchStatus.not_a_match
    assert "#### Blocking issues" in report
    assert "#### Other checks that matched but do not override the blocking issue" in report
    assert "#### Documents to prepare" not in report


def test_save_agent_outputs_writes_report_and_trace(
    tmp_path: Path,
    full_pragati_profile: CitizenProfile,
) -> None:
    search_results = search_schemes_for_profile(full_pragati_profile)
    eligibility = check_eligibility_for_scheme(
        profile=full_pragati_profile,
        scheme=search_results[0].scheme,
    )

    result = AgentRunResult(
        profile=full_pragati_profile,
        search_results=search_results,
        eligibility_results=[eligibility],
        steps=[],
        needs_follow_up=False,
        follow_up_questions=[],
        final_message=eligibility.user_message,
    )

    saved_paths = save_agent_outputs(
        result=result,
        output_dir=tmp_path,
    )

    assert Path(saved_paths.report_path).exists()
    assert Path(saved_paths.trace_path).exists()
    assert Path(saved_paths.latest_report_path).exists()
    assert Path(saved_paths.latest_trace_path).exists()

    latest_report_text = Path(saved_paths.latest_report_path).read_text(
        encoding="utf-8"
    )

    assert "SevaSathi AI Readiness Report" in latest_report_text
