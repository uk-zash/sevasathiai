"""Command-line smoke run for the SevaSathi TAOR agent."""

from app.output_writer import save_agent_outputs
from app.taor_agent import SevaSathiTAORAgent


def main() -> None:
    """Run the agent with a representative profile and save output artifacts."""
    # This sample intentionally contains enough details to exercise extraction,
    # search, eligibility, ranking, and report writing in one local run.
    user_text = (
        "I am 20 years old and I live in Maharashtra. "
        "I am a female student with 45 percent disability. "
        "I am doing B.Tech first year in an AICTE-approved college. "
        "My family income is around 2 lakh per year. "
        "I have a valid income certificate. "
        "There are 2 girl children in my family. "
        "I am not receiving any other scholarship."
    )

    agent = SevaSathiTAORAgent()
    result = agent.run(user_text)

    # Persist both a human-readable report and the structured trace for debugging.
    saved_files = save_agent_outputs(result)

    print("FINAL MESSAGE")
    print("=" * 60)
    print(result.final_message)

    print("\nRANKED RESULTS")
    print("=" * 60)

    for ranked in result.ranked_results:
        print(
            ranked.search_result.scheme.scheme_id,
            ranked.recommendation_label.value,
            ranked.rank_score,
            ranked.eligibility_result.status.value,
        )

    print("\nSAVED FILES")
    print("=" * 60)
    print(f"Report: {saved_files.report_path}")
    print(f"Trace: {saved_files.trace_path}")


if __name__ == "__main__":
    main()
