"""Streamlit UI for the SevaSathi AI readiness assistant.

This file is the user-facing entry point. It owns browser/session state, renders
the initial details form, renders follow-up forms, and stores the latest agent
result/report/trace for display and download.
"""

import re

import streamlit as st

from app.follow_up_parser import profile_update_from_follow_up_answers
from app.output_writer import build_markdown_report, save_agent_outputs
from app.profile_merge import merge_citizen_profiles
from app.taor_agent import SevaSathiTAORAgent


SELECT_OPTION = "Select an answer"
OTHER_OPTION = "Other"
PREFER_NOT_TO_SAY_OPTION = "Prefer not to say"

INDIAN_STATES_AND_UTS = [
    SELECT_OPTION,
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    PREFER_NOT_TO_SAY_OPTION,
    OTHER_OPTION,
]

COURSE_OPTIONS = [
    SELECT_OPTION,
    "B.Tech",
    "B.E.",
    "Diploma",
    "BA",
    "BSc",
    "BCom",
    "BCA",
    "BBA",
    "MBBS",
    "ITI / Vocational",
    "Class 12",
    PREFER_NOT_TO_SAY_OPTION,
    OTHER_OPTION,
]


def _format_number_answer(value, suffix: str = "") -> str:
    """Convert optional Streamlit numeric input values into parser-friendly text."""
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        value_text = str(int(value))
    else:
        value_text = str(value)

    return f"{value_text} {suffix}".strip()


def initialize_session_state() -> None:
    """Create all Streamlit session keys used across reruns.

    Streamlit reruns the script after every form submit or button click. These
    keys keep the current profile, latest result, original search query, and
    generated downloads alive across those reruns.
    """
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

    if "search_query_text" not in st.session_state:
        st.session_state.search_query_text = ""


def reset_session() -> None:
    """Clear all user/session data and return the UI to the first form."""
    st.session_state.profile = None
    st.session_state.result = None
    st.session_state.report_markdown = ""
    st.session_state.trace_json = ""
    st.session_state.saved_files = None
    st.session_state.follow_up_round = 0
    st.session_state.search_query_text = ""


def run_agent_and_store_result(
    user_text: str,
    existing_profile=None,
    search_query_text=None,
) -> None:
    """Run the TAOR agent and persist its result in Streamlit state.

    Args:
        user_text: Current user input. For follow-up rounds this is a
            question/answer context block, not necessarily the original query.
        existing_profile: Previous profile to merge with the newly extracted
            profile. `None` means this is the first turn.
        search_query_text: Original user intent to preserve across follow-ups.
    """
    if existing_profile is None:
        # Preserve the first user request so short follow-up answers like "Yes"
        # do not replace the query used for scheme retrieval.
        st.session_state.search_query_text = user_text

    effective_search_query_text = (
        search_query_text
        or st.session_state.search_query_text
        or user_text
    )

    agent = SevaSathiTAORAgent()
    result = agent.run(
        user_text=user_text,
        existing_profile=existing_profile,
        search_query_text=effective_search_query_text,
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
    """Build an LLM-readable context block from follow-up form answers.

    The question text is included because answers like "yes", "no", or
    "first year" only make sense when the extractor sees the question too.
    """
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
    """Render and process the follow-up form for missing profile details."""
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
            with st.container(border=True):
                st.markdown(f"**Question {index}**")
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
        # Keep only answered questions; skipped questions remain unknown.
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
        # Deterministic parsing handles structured UI answers immediately.
        # The LLM still receives the same answers as backup/context.
        deterministic_profile_update = profile_update_from_follow_up_answers(answered_pairs)
        merged_profile = merge_citizen_profiles(
            existing_profile=st.session_state.profile,
            update=deterministic_profile_update,
        )

        with st.spinner("Updating your profile and checking again..."):
            run_agent_and_store_result(
                user_text=follow_up_context,
                existing_profile=merged_profile,
                search_query_text=st.session_state.search_query_text,
            )

        st.session_state.follow_up_round += 1
        st.rerun()

def show_result() -> None:
    """Render the current result state: follow-up, no-match, or final guidance."""
    result = st.session_state.result

    if result is None:
        return

    if result.needs_follow_up:
        # While follow-up is pending, hide scheme analysis so users focus on
        # supplying missing details before recommendations are shown.
        st.subheader("More information needed")
        st.warning("More details are needed before stronger guidance can be given.")
        st.markdown(result.final_message)
        render_follow_up_form()
        return

    if not result.search_results and not result.eligibility_results and not result.ranked_results:
        # Clean no-match state: no scheme-by-scheme rejection analysis here.
        st.subheader("No match found")
        st.info("No verified match was found from the current local database.")
        st.markdown(result.final_message)
        return

    st.subheader("Final guidance")
    st.success("The agent completed this readiness check.")

    st.markdown(result.final_message)

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
    """Configure the Streamlit page and route to initial form or result view."""
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
    """Choose the best Streamlit widget for a follow-up question.

    Args:
        question: User-facing follow-up question generated by the agent.
        index: 1-based position used to create stable widget keys.

    Returns:
        The answer text selected/entered by the user, or an empty string when
        the user leaves the question unanswered.
    """
    normalized = question.lower()
    # Include the follow-up round in keys so old widget values do not bleed into
    # the next round after `st.rerun()`.
    key_prefix = f"follow_up_{st.session_state.follow_up_round}_{index}"

    if (
        "which indian state" in normalized
        or "which state" in normalized
        or "union territory do you live" in normalized
    ):
        answer = st.selectbox(
            label=f"Your answer to question {index}",
            options=INDIAN_STATES_AND_UTS,
            key=f"{key_prefix}_state",
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        if answer == OTHER_OPTION:
            return st.text_input(
                label="Enter your state or union territory",
                placeholder="Example: Maharashtra, Karnataka, Delhi",
                key=f"{key_prefix}_state_other",
            )

        return answer

    if "district" in normalized:
        return st.text_input(
            label=f"Your answer to question {index}",
            placeholder="Example: Pune, Bengaluru Urban, New Delhi",
            key=f"{key_prefix}_district",
            label_visibility="collapsed",
        )

    if re.search(r"\bage\b", normalized):
        answer = st.number_input(
            label=f"Your answer to question {index}",
            min_value=0,
            max_value=120,
            value=None,
            step=1,
            key=f"{key_prefix}_age",
            label_visibility="collapsed",
        )

        return _format_number_answer(answer)

    if "girl-student condition" in normalized or "gender" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, I am a girl/female student for this scheme",
                "No, I am not a girl/female student for this scheme",
                PREFER_NOT_TO_SAY_OPTION,
            ],
            key=f"{key_prefix}_gender",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "currently a student" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, I am currently a student",
                "No, I am not currently a student",
            ],
            key=f"{key_prefix}_student_status",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "education level" in normalized:
        answer = st.selectbox(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "School",
                "Undergraduate",
                "Postgraduate",
                "Diploma",
                "Vocational",
                "Not applicable",
            ],
            key=f"{key_prefix}_education_level",
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "first year" in normalized or "lateral entry" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "First year regular admission",
                "Second year lateral entry",
                "Continuing student / later year",
                "I do not know",
            ],
            key=f"{key_prefix}_admission_type",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "type of institution" in normalized or "institution type" in normalized:
        answer = st.selectbox(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Government",
                "Private",
                "Aided",
                "Open university",
                "I do not know",
            ],
            key=f"{key_prefix}_institution_type",
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "course" in normalized:
        answer = st.selectbox(
            label=f"Your answer to question {index}",
            options=COURSE_OPTIONS,
            key=f"{key_prefix}_course",
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        if answer == OTHER_OPTION:
            return st.text_input(
                label="Enter your course",
                placeholder="Example: B.Tech, B.E., diploma, BA, BSc",
                key=f"{key_prefix}_course_other",
            )

        return answer

    if "aicte" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, my institution is AICTE-approved",
                "No, my institution is not AICTE-approved",
                "I do not know",
            ],
            key=f"{key_prefix}_aicte",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "family income" in normalized:
        income_unit = st.selectbox(
            label="Income unit",
            options=["INR per year", "Lakh per year"],
            key=f"{key_prefix}_income_unit",
        )
        amount = st.number_input(
            label=f"Your answer to question {index}",
            min_value=0.0,
            value=None,
            step=0.1 if income_unit == "Lakh per year" else 1000.0,
            key=f"{key_prefix}_income",
            label_visibility="collapsed",
        )

        if income_unit == "Lakh per year":
            return _format_number_answer(amount, "lakh")

        return _format_number_answer(amount)

    if "income certificate" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, I have a valid income certificate",
                "No, I do not have one yet",
                "I do not know",
            ],
            key=f"{key_prefix}_income_certificate",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "girl children" in normalized:
        answer = st.number_input(
            label=f"Your answer to question {index}",
            min_value=0,
            max_value=20,
            value=None,
            step=1,
            key=f"{key_prefix}_girl_children",
            label_visibility="collapsed",
        )

        return _format_number_answer(answer)

    if "other scholarship" in normalized or "financial assistance" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "No, I am not receiving another scholarship or financial assistance",
                "Yes, I am receiving another scholarship or financial assistance",
                "I do not know",
            ],
            key=f"{key_prefix}_other_scholarship",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "minority" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, I belong to a minority community",
                "No, I do not belong to a minority community",
                PREFER_NOT_TO_SAY_OPTION,
            ],
            key=f"{key_prefix}_minority_status",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "social category" in normalized:
        answer = st.selectbox(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "General",
                "SC",
                "ST",
                "OBC",
                "EWS",
                PREFER_NOT_TO_SAY_OPTION,
            ],
            key=f"{key_prefix}_social_category",
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "category-based" in normalized or "category based" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, consider category-based schemes",
                "No, do not consider category-based schemes",
            ],
            key=f"{key_prefix}_category_based",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    if "disability percentage" in normalized:
        prefer_not_to_say = st.checkbox(
            "Prefer not to say",
            key=f"{key_prefix}_disability_percentage_skip",
        )

        if prefer_not_to_say:
            return PREFER_NOT_TO_SAY_OPTION

        answer = st.number_input(
            label=f"Your answer to question {index}",
            min_value=0,
            max_value=100,
            value=None,
            step=1,
            key=f"{key_prefix}_disability_percentage",
            label_visibility="collapsed",
        )

        return _format_number_answer(answer, "percent")

    if "disability condition" in normalized or "disability status" in normalized or "specially-abled" in normalized:
        answer = st.radio(
            label=f"Your answer to question {index}",
            options=[
                SELECT_OPTION,
                "Yes, I have a disability",
                "No, I do not have a disability",
                PREFER_NOT_TO_SAY_OPTION,
            ],
            key=f"{key_prefix}_disability_status",
            horizontal=True,
            label_visibility="collapsed",
        )

        if answer == SELECT_OPTION:
            return ""

        return answer

    return st.text_area(
        label=f"Your answer to question {index}",
        placeholder="Type your answer here.",
        height=80,
        key=f"{key_prefix}_generic",
        label_visibility="collapsed",
    )

if __name__ == "__main__":
    main()
