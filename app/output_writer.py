"""Build Markdown/JSON artifacts for an agent run."""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    AgentRunResult,
    EligibilityResult,
    MatchStatus,
    SchemeSearchResult
)

DEFAULT_OUTPUT_DIR = Path("outputs")


class SavedOutputPaths(BaseModel):
    """File paths created when a run is saved to disk."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    output_dir: str = Field(
        description="Directory where output files were saved.",
    )

    report_path: str = Field(
        description="Timestamped Markdown report path.",
    )

    trace_path: str = Field(
        description="Timestamped JSON trace path.",
    )

    latest_report_path: str = Field(
        description="Stable path pointing to the latest Markdown report.",
    )

    latest_trace_path: str = Field(
        description="Stable path pointing to the latest JSON trace.",
    )


def _display_value(value: Any) -> str:
    """Format profile values for Markdown without leaking Python enum objects."""
    if value is None:
        return "Not provided"

    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


def _find_search_result_for_eligibility(
    eligibility: EligibilityResult,
    search_results: list[SchemeSearchResult],
) -> Optional[SchemeSearchResult]:
    """Find the scheme metadata associated with an eligibility result."""
    for search_result in search_results:
        if search_result.scheme.scheme_id == eligibility.scheme_id:
            return search_result

    return None


def _append_eligibility_details(
    lines: list[str],
    eligibility: EligibilityResult,
    search_result: Optional[SchemeSearchResult],
) -> None:
    """Append one scheme's detailed eligibility section to a Markdown buffer.

    Args:
        lines: Mutable report line buffer.
        eligibility: Rule-check result to render.
        search_result: Matching scheme metadata, if the scheme was part of
            search results.
    """
    scheme_name = eligibility.scheme_id

    if search_result:
        scheme_name = search_result.scheme.name

    lines.append(f"### {scheme_name}")
    lines.append("")
    lines.append(f"- Status: `{eligibility.status.value}`")
    lines.append(f"- Confidence: `{eligibility.confidence}`")
    lines.append("")
    lines.append(eligibility.user_message)
    lines.append("")

    if eligibility.not_matched_reasons:
        lines.append("#### Blocking issues")
        lines.append("")
        for reason in eligibility.not_matched_reasons:
            lines.append(f"- {reason}")
        lines.append("")

    if eligibility.matched_reasons:
        if eligibility.status == MatchStatus.not_a_match:
            lines.append("#### Other checks that matched but do not override the blocking issue")
        else:
            lines.append("#### Matched checks")

        lines.append("")
        for reason in eligibility.matched_reasons:
            lines.append(f"- {reason}")
        lines.append("")

    if eligibility.missing_information:
        lines.append("#### Missing or uncertain information")
        lines.append("")
        for item in eligibility.missing_information:
            lines.append(f"- {item}")
        lines.append("")

    if not search_result:
        return

    scheme = search_result.scheme

    if scheme.required_documents and eligibility.status != MatchStatus.not_a_match:
        lines.append("#### Documents to prepare")
        lines.append("")
        for document in scheme.required_documents:
            lines.append(f"- {document}")
        lines.append("")

    if scheme.application_window:
        lines.append("#### Application window")
        lines.append("")
        lines.append(f"- Status: {scheme.application_window.status.value}")
        lines.append(f"- Academic year: {scheme.application_window.academic_year}")
        lines.append(f"- Opens at: {scheme.application_window.opens_at}")
        lines.append(f"- Student deadline: {scheme.application_window.student_deadline}")
        lines.append(
            f"- Institute verification deadline: "
            f"{scheme.application_window.institute_verification_deadline}"
        )
        lines.append(
            f"- Final verification deadline: "
            f"{scheme.application_window.final_verification_deadline}"
        )
        lines.append("")

    lines.append("#### Official sources")
    lines.append("")
    for source in scheme.sources:
        lines.append(f"- {source.publisher}: {source.title}")
        lines.append(f"  - URL: {source.url}")
        lines.append(f"  - Last checked: {source.last_checked_at}")
    lines.append("")


def build_markdown_report(result: AgentRunResult) -> str:
    """Render the full agent result as a Markdown readiness report."""
    lines: list[str] = []

    lines.append("# SevaSathi AI Readiness Report")
    lines.append("")
    lines.append(
        "> This report is readiness guidance, not final eligibility. "
        "Always verify details and apply only through the official portal."
    )
    lines.append("")

    lines.append("## Final guidance")
    lines.append("")
    lines.append(result.final_message)
    lines.append("")

    if result.profile:
        profile = result.profile

        lines.append("## Extracted user profile")
        lines.append("")
        lines.append(f"- Age: {_display_value(profile.age)}")
        lines.append(f"- State: {_display_value(profile.state)}")
        lines.append(f"- District: {_display_value(profile.district)}")
        lines.append(f"- Gender: {_display_value(profile.gender)}")
        lines.append(f"- Is student: {_display_value(profile.is_student)}")
        lines.append(f"- Education level: {_display_value(profile.education_level)}")
        lines.append(f"- Course name: {_display_value(profile.course_name)}")
        lines.append(f"- Institution type: {_display_value(profile.institution_type)}")
        lines.append(f"- Admission type: {_display_value(profile.admission_type)}")
        lines.append(
            f"- AICTE-approved institution: {_display_value(profile.is_aicte_approved_institution)}"
        )
        lines.append(f"- Annual family income: {_display_value(profile.annual_family_income)}")
        lines.append(
            f"- Valid income certificate available: {_display_value(profile.has_valid_income_certificate)}"
        )
        lines.append(f"- Girl children in family: {_display_value(profile.girl_children_in_family)}")
        lines.append(
            f"- Receiving other scholarship: {_display_value(profile.receiving_other_scholarship)}"
        )
        lines.append("")

    if result.ranked_results:
        lines.append("## Ranked scheme checks")
        lines.append("")

        for index, ranked in enumerate(result.ranked_results, start=1):
            eligibility = ranked.eligibility_result
            search_result = ranked.search_result
            scheme = search_result.scheme

            lines.append(f"### {index}. {scheme.name}")
            lines.append("")
            lines.append(f"- Recommendation: `{ranked.recommendation_label.value}`")
            lines.append(f"- Rank score: `{ranked.rank_score}`")
            lines.append(f"- Status: `{eligibility.status.value}`")
            lines.append(f"- Confidence: `{eligibility.confidence}`")
            lines.append("")

            if ranked.rank_reasons:
                lines.append("#### Why this ranking?")
                lines.append("")
                for reason in ranked.rank_reasons:
                    lines.append(f"- {reason}")
                lines.append("")

            search_result = _find_search_result_for_eligibility(
                eligibility=eligibility,
                search_results=result.search_results,
            )

            _append_eligibility_details(
                lines=lines,
                eligibility=eligibility,
                search_result=search_result,
            )

    elif result.eligibility_results:
        lines.append("## Scheme checks")
        lines.append("")

        for eligibility in result.eligibility_results:
            search_result = _find_search_result_for_eligibility(
                eligibility=eligibility,
                search_results=result.search_results,
            )
            _append_eligibility_details(
                lines=lines,
                eligibility=eligibility,
                search_result=search_result,
            )

    if result.follow_up_questions:
        lines.append("## Follow-up questions")
        lines.append("")
        for question in result.follow_up_questions:
            lines.append(f"- {question}")
        lines.append("")

    if result.steps:
        lines.append("## TAOR trace summary")
        lines.append("")

        for step in result.steps:
            lines.append(f"### Step {step.step_number}")
            lines.append("")
            lines.append(f"- Think: {step.thought}")
            lines.append(f"- Act: `{step.action.value}`")
            lines.append(f"- Observe: {step.observation}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by SevaSathi AI. This tool does not collect Aadhaar numbers, OTPs, "
        "bank account numbers, or certificate IDs."
    )

    return "\n".join(lines)


def save_agent_outputs(
    result: AgentRunResult,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> SavedOutputPaths:
    """Save timestamped and latest Markdown/JSON outputs for one agent run."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Timestamped files preserve history, while latest_* paths are convenient
    # for quickly opening the newest run.
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = output_dir / f"report_{run_id}.md"
    trace_path = output_dir / f"trace_{run_id}.json"

    latest_report_path = output_dir / "latest_report.md"
    latest_trace_path = output_dir / "latest_trace.json"

    report_text = build_markdown_report(result)
    trace_text = result.model_dump_json(indent=2)

    report_path.write_text(report_text, encoding="utf-8")
    trace_path.write_text(trace_text, encoding="utf-8")

    latest_report_path.write_text(report_text, encoding="utf-8")
    latest_trace_path.write_text(trace_text, encoding="utf-8")

    return SavedOutputPaths(
        output_dir=str(output_dir),
        report_path=str(report_path),
        trace_path=str(trace_path),
        latest_report_path=str(latest_report_path),
        latest_trace_path=str(latest_trace_path),
    )
