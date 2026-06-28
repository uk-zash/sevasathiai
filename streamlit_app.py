import streamlit as st

from app.output_writer import build_markdown_report, save_agent_outputs
from app.taor_agent import SevaSathiTAORAgent


def initialize_session_state() -> None:
    if "profile" not in st.session_state:
        st.session_state.profile = None

    if "result" not in st.session_state:
        st.session_state.result = None

    if "report_markdown" not in st.session_state:
        st.session_state.report_markdown = ""

    if "trace_json" not in st.session_state:
        st.session_state.trace_json = ""

    if "saved_files" not in st.session_state:
        st.session_state.saved_files = None

    if "follow_up_round" not in st.session_state:
        st.session_state.follow_up_round = 0


def reset_session() -> None:
    st.session_state.profile = None
    st.session_state.result = None
    st.session_state.report_markdown = ""
    st.session_state.trace_json = ""
    st.session_state.saved_files = None
    st.session_state.follow_up_round = 0


def run_agent_and_store_result(
    user_text: str,
    existing_profile=None,
) -> None:
    agent = SevaSathiTAORAgent()
    result = agent.run(
        user_text=user_text,
        existing_profile=existing_profile,
    )

    saved_files = save_agent_outputs(result)
    report_markdown = build_markdown_report(result)
    trace_json = result.model_dump_json(indent=2)

    st.session_state.profile = result.profile
    st.session_state.result = result
    st.session_state.saved_files = saved_files
    st.session_state.report_markdown = report_markdown
    st.session_state.trace_json = trace_json


def build_follow_up_context_from_answers(
    question_answer_pairs: list[tuple[str, str]],
) -> str:
    blocks: list[str] = []

    for index, (question, answer) in enumerate(question_answer_pairs, start=1):
        clean_answer = answer.strip()

        if not clean_answer:
            continue

        blocks.append(
            f"Question {index}: {question}\n"
            f"Answer {index}: {clean_answer}"
        )

    return (
        "The user is answering follow-up questions from SevaSathi AI.\n"
        "Use each question as context for the answer. "
        "Extract only clearly stated profile details.\n\n"
        + "\n\n".join(blocks)
    )


def render_follow_up_form() -> None:
    result = st.session_state.result

    if result is None or not result.needs_follow_up:
        return

    st.divider()
    st.subheader("Answer the next questions")

    st.caption(
        "Please answer the questions below. Answer only what you know. "
        "You may skip anything you are not comfortable sharing. "
        "Do not share Aadhaar numbers, OTPs, bank account numbers, or certificate IDs."
    )

    current_questions = result.follow_up_questions

    with st.form("follow_up_form"):
        question_answer_pairs: list[tuple[str, str]] = []

        for index, question in enumerate(current_questions, start=1):
            st.markdown(f"### Question {index}")
            st.write(question)

            answer = render_follow_up_answer_input(
                question=question,
                index=index,
            )

            question_answer_pairs.append((question, answer))

        st.markdown("### Additional details")

        extra_details = st.text_area(
            label="Anything else you want to add? Optional",
            key=f"follow_up_{st.session_state.follow_up_round}_extra",
            placeholder=(
                "Example: There are 2 girl children in my family. "
                "I am not receiving any other scholarship."
            ),
            height=100,
        )

        follow_up_submitted = st.form_submit_button("Update my answer")

    if follow_up_submitted:
        answered_pairs = [
            (question, answer)
            for question, answer in question_answer_pairs
            if answer.strip()
        ]

        if extra_details.strip():
            answered_pairs.append(("Additional details", extra_details))

        if not answered_pairs:
            st.warning("Please answer at least one follow-up question.")
            return

        follow_up_context = build_follow_up_context_from_answers(answered_pairs)

        with st.spinner("Updating your profile and checking again..."):
            run_agent_and_store_result(
                user_text=follow_up_context,
                existing_profile=st.session_state.profile,
            )

        st.session_state.follow_up_round += 1
        st.rerun()

def show_result() -> None:
    result = st.session_state.result

    if result is None:
        return

    if result.needs_follow_up:
        st.subheader("Current assessment")
        st.warning("More details are needed before stronger guidance can be given.")
    else:
        st.subheader("Final guidance")
        st.success("The agent completed this readiness check.")

    st.markdown(result.final_message)

    if result.needs_follow_up:
        render_follow_up_form()

    tab_profile, tab_schemes, tab_trace, tab_report = st.tabs(
        ["Extracted profile", "Scheme checks", "TAOR trace", "Report"]
    )

    with tab_profile:
        if result.profile:
            st.json(result.profile.model_dump(mode="json"))
        else:
            st.info("No profile was extracted.")

    with tab_schemes:
        if result.ranked_results:
            for index, ranked in enumerate(result.ranked_results, start=1):
                scheme = ranked.search_result.scheme
                eligibility = ranked.eligibility_result

                st.markdown(f"### {index}. {scheme.name}")
                st.write(f"Recommendation: `{ranked.recommendation_label.value}`")
                st.write(f"Rank score: `{ranked.rank_score}`")
                st.write(f"Eligibility status: `{eligibility.status.value}`")
                st.write(f"Confidence: `{eligibility.confidence}`")

                with st.expander("Why this ranking?"):
                    for reason in ranked.rank_reasons:
                        st.write(f"- {reason}")

                st.write(eligibility.user_message)

                if eligibility.not_matched_reasons:
                    st.markdown("**Blocking issues**")
                    for reason in eligibility.not_matched_reasons:
                        st.write(f"- {reason}")

                if eligibility.matched_reasons:
                    if eligibility.status.value == "not_a_match":
                        st.markdown("**Other checks that matched but do not override the blocking issue**")
                    else:
                        st.markdown("**Matched checks**")

                    for reason in eligibility.matched_reasons:
                        st.write(f"- {reason}")

                if eligibility.missing_information:
                    st.markdown("**Missing or uncertain information**")
                    for item in eligibility.missing_information:
                        st.write(f"- {item}")

                st.divider()

        elif result.eligibility_results:
            for eligibility in result.eligibility_results:
                st.markdown(f"### {eligibility.scheme_id}")
                st.write(f"Status: `{eligibility.status.value}`")
                st.write(f"Confidence: `{eligibility.confidence}`")
                st.write(eligibility.user_message)
        else:
            st.info("No scheme checks were completed.")

    with tab_trace:
        for step in result.steps:
            st.markdown(f"### Step {step.step_number}")
            st.write(f"**Think:** {step.thought}")
            st.write(f"**Act:** `{step.action.value}`")
            st.write(f"**Observe:** {step.observation}")

            with st.expander("Step data"):
                st.json(step.data)

    with tab_report:
        st.markdown(st.session_state.report_markdown)

    st.subheader("Downloads")

    st.download_button(
        label="Download Markdown report",
        data=st.session_state.report_markdown,
        file_name="sevasathi_report.md",
        mime="text/markdown",
    )

    st.download_button(
        label="Download JSON trace",
        data=st.session_state.trace_json,
        file_name="sevasathi_trace.json",
        mime="application/json",
    )

    if st.session_state.saved_files:
        st.caption(f"Saved latest report locally at: {st.session_state.saved_files.latest_report_path}")
        st.caption(f"Saved latest trace locally at: {st.session_state.saved_files.latest_trace_path}")


def main() -> None:
    st.set_page_config(
        page_title="SevaSathi AI",
        page_icon="🪔",
        layout="wide",
    )

    initialize_session_state()

    st.title("SevaSathi AI")
    st.caption("Verified welfare and scholarship readiness assistant")

    st.info(
        "Do not enter Aadhaar numbers, OTPs, bank account numbers, certificate IDs, "
        "or other sensitive identifiers. This tool gives readiness guidance, not final eligibility."
    )

    with st.sidebar:
        st.header("Session")

        if st.button("Start new session"):
            reset_session()
            st.rerun()

        st.markdown("### Current state")

        if st.session_state.profile:
            st.success("Profile available")
        else:
            st.warning("No profile yet")

        if st.session_state.result and st.session_state.result.needs_follow_up:
            st.warning("Follow-up needed")
        elif st.session_state.result:
            st.success("Latest check completed")

    if st.session_state.result is None:
        with st.form("initial_details_form"):
            user_text = st.text_area(
                "Tell me about the student and what help is needed",
                placeholder=(
                    "Example: I am a 21-year-old female B.Tech student from Maharashtra. "
                    "My family income is around 1.8 lakh per year. I need scholarship help."
                ),
                height=160,
            )

            submitted = st.form_submit_button("Analyze")

        if submitted:
            if not user_text.strip():
                st.warning("Please enter some details before analyzing.")
            else:
                with st.spinner("Running TAOR agent..."):
                    run_agent_and_store_result(
                        user_text=user_text,
                        existing_profile=None,
                    )

                st.rerun()

    else:
        show_result()


def render_follow_up_answer_input(question: str, index: int) -> str:
    normalized = question.lower()
    key_prefix = f"follow_up_{st.session_state.follow_up_round}_{index}"

    if "girl-student condition" in normalized or "gender" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "Yes, this condition applies to me",
                "No, this condition does not apply to me",
                "Prefer not to say",
            ],
            key=f"{key_prefix}_gender",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "currently a student" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "Yes, I am currently a student",
                "No, I am not currently a student",
            ],
            key=f"{key_prefix}_student_status",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "education level" in normalized:
        answer = st.selectbox(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "School",
                "Undergraduate",
                "Postgraduate",
                "Diploma",
                "Vocational",
                "Not applicable",
            ],
            key=f"{key_prefix}_education_level",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "course" in normalized:
        return st.text_input(
            label=f"Your answer to question {index}",
            placeholder="Example: B.Tech, B.E., diploma, BA, BSc",
            key=f"{key_prefix}_course",
        )

    if "first year" in normalized or "lateral entry" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "First year regular admission",
                "Second year lateral entry",
                "Continuing student / later year",
                "I do not know",
            ],
            key=f"{key_prefix}_admission_type",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "aicte" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "Yes, my institution is AICTE-approved",
                "No, my institution is not AICTE-approved",
                "I do not know",
            ],
            key=f"{key_prefix}_aicte",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "family income" in normalized:
        return st.text_input(
            label=f"Your answer to question {index}",
            placeholder="Example: 180000 or 1.8 lakh",
            key=f"{key_prefix}_income",
        )

    if "income certificate" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "Yes, I have a valid income certificate",
                "No, I do not have one yet",
                "I do not know",
            ],
            key=f"{key_prefix}_income_certificate",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "girl children" in normalized:
        return st.text_input(
            label=f"Your answer to question {index}",
            placeholder="Example: 1, 2, 3, or Prefer not to say",
            key=f"{key_prefix}_girl_children",
        )

    if "other scholarship" in normalized or "financial assistance" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "No, I am not receiving another scholarship or financial assistance",
                "Yes, I am receiving another scholarship or financial assistance",
                "I do not know",
            ],
            key=f"{key_prefix}_other_scholarship",
        )

        if answer == "Select an answer":
            return ""

        return answer
    if "disability condition" in normalized or "disability status" in normalized or "specially-abled" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                "Select an answer",
                "Yes, the disability condition applies to me",
                "No, the disability condition does not apply to me",
                "Prefer not to say",
            ],
            key=f"{key_prefix}_disability_status",
        )

        if answer == "Select an answer":
            return ""

        return answer

    if "disability percentage" in normalized:
        return st.text_input(
            label=f"Your answer to question {index}",
            placeholder="Example: 40%, 55%, 75 percent, or Prefer not to say",
            key=f"{key_prefix}_disability_percentage",
        )

    return st.text_area(
        label=f"Your answer to question {index}",
        placeholder="Type your answer here.",
        height=80,
        key=f"{key_prefix}_generic",
    )

if __name__ == "__main__":
    main()