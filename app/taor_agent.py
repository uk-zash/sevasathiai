"""TAOR-style orchestration for SevaSathi AI.

The agent coordinates the full reasoning loop:
profile extraction -> scheme search -> eligibility checks -> ranking ->
follow-up questions or final guidance.
"""

from app.eligibility_checker import  check_eligibility_for_scheme
from app.models import (
    AgentAction,
    AgentRunResult,
    AgentStep,
    CitizenProfile,
    EligibilityRule,
    EligibilityResult,
    MatchStatus,
    RankedSchemeResult,
    RecommendationLabel,
    RuleOperator,
    Scheme,
    SchemeSearchResult,
)

from app.ranking import rank_scheme_results
from app.profile_merge import get_basic_missing_profile_fields, merge_citizen_profiles

from app.profile_extractor import extract_profile_from_text
from app.scheme_search import search_schemes_for_profile
from typing import Optional

FIELD_QUESTION_MAP = {
    # Maps CitizenProfile fields to user-facing follow-up questions. New schemes
    # work generically when their EligibilityRule.field_name exists here or can
    # fall back to `_question_for_rule`.
    "age": "What is your age?",
    "state": "Which Indian state or union territory do you live in?",
    "district": "Which district do you live in?",
    "gender": (
        "Does the girl-student condition apply to you for this scheme? "
        "You may answer Yes, No, or Prefer not to say."
    ),
    "is_student": "Are you currently a student?",
    "education_level": (
        "What is your current education level? "
        "For example: school, undergraduate, postgraduate, diploma, or vocational."
    ),
    "course_name": (
        "What course are you studying? "
        "For example: B.Tech, B.E., diploma, BA, BSc, or another course."
    ),
    "institution_type": "What type of institution do you study in?",
    "admission_type": (
        "Were you admitted into the first year normally, "
        "or into the second year through lateral entry?"
    ),
    "is_aicte_approved_institution": "Is your institution AICTE-approved?",
    "annual_family_income": "What is your approximate annual family income in INR?",
    "has_valid_income_certificate": "Do you have a valid income certificate issued by your State or UT Government?",
    "girl_children_in_family": (
        "How many girl children are in your family? "
        "You may skip this if you are not comfortable sharing."
    ),
    "receiving_other_scholarship": "Are you currently receiving any other scholarship or financial assistance?",
    "social_category": "What is your social category? You may answer General, SC, ST, OBC, EWS, or Prefer not to say.",
    "has_disability": (
        "Does the specially-abled or disability condition apply to you for this scheme? "
        "You may answer Yes, No, or Prefer not to say."
    ),
    "disability_percentage": (
        "What is your disability percentage as mentioned on your disability certificate? "
        "You may skip this if you are not comfortable sharing."
    ),
    "minority_status": "Do you belong to a minority community? You may answer Yes, No, or Prefer not to say.",
    "wants_category_based_schemes": "Do you want category-based schemes to be considered?",
}


def _field_label(field_name: str) -> str:
    """Convert a profile field name into readable text for fallback questions."""
    return field_name.replace("_", " ")


class SevaSathiTAORAgent:
    """Runs one complete SevaSathi AI decision loop.

    Args:
        max_candidate_checks: Maximum number of searched candidate schemes that
            will receive expensive rule-based eligibility checks.
    """

    def __init__(self , max_candidate_checks: int = 3) -> None:
        if max_candidate_checks < 1 :
            raise ValueError("max_candidate_checks must be atleast 1")
        
        self.max_candidate_checks = max_candidate_checks

    
    def run(
        self,
        user_text: str,
        existing_profile: Optional[CitizenProfile] = None,
        search_query_text: Optional[str] = None,
    ) -> AgentRunResult:
        """Run the assistant for an initial query or follow-up answer.

        Args:
            user_text: Current user message. For follow-up rounds this can be a
                generated question/answer context block.
            existing_profile: Previously extracted profile, if this is a
                follow-up round.
            search_query_text: Original user request used for retrieval across
                follow-ups so short answers do not change search intent.

        Returns:
            AgentRunResult containing the merged profile, trace steps, search
            results, eligibility results, ranked results, follow-up questions,
            and final user-facing message.
        """
        steps: list[AgentStep] = []
        step_number = 1

        def add_step(
            thought: str,
            action: AgentAction,
            observation: str,
            data: Optional[dict] = None, 
        ) -> None:
            """Append a structured trace step for debugging and UI display."""
            nonlocal step_number

            steps.append(
                AgentStep(
                    step_number=step_number,
                    thought=thought,
                    action=action,
                    observation=observation,
                    data=data or {},
                )
            )

            step_number += 1

        # Step 1: extract a structured profile from the latest text.
        extraction = extract_profile_from_text(user_text)
        profile = merge_citizen_profiles(
            existing_profile=existing_profile,
            update=extraction.profile,
        )
        basic_missing_fields = get_basic_missing_profile_fields(profile)

        if existing_profile is None:
            profile_observation = (
                f"Extracted citizen profile with confidence {extraction.confidence}. "
                f"Important missing fields: {', '.join(basic_missing_fields) if basic_missing_fields else 'none'}."
            )
        else:
            profile_observation = (
                f"Extracted follow-up details with confidence {extraction.confidence} "
                "and merged them into the existing profile. "
                f"Important missing fields after merge: {', '.join(basic_missing_fields) if basic_missing_fields else 'none'}."
            )

        add_step(
            thought="I need to understand the user's profile before searching for schemes.",
            action=AgentAction.extract_profile,
            observation=profile_observation,
            data={
                "newly_extracted_profile": extraction.profile.model_dump(mode="json"),
                "merged_profile": profile.model_dump(mode="json"),
                "extractor_missing_fields": extraction.missing_fields,
                "important_missing_fields_after_merge": basic_missing_fields,
                "assumptions": extraction.assumptions,
                "privacy_warnings": extraction.privacy_warnings,
            },
        )

        # Step 2: retrieve candidate schemes using the merged profile and the
        # original search intent.
        search_results = search_schemes_for_profile(
            profile,
            query_text=search_query_text or user_text,
        )

        add_step(
            thought="Now I should search the verified scheme database using the extracted profile.",
            action=AgentAction.search_schemes,
            observation=f"Found {len(search_results)} candidate scheme(s).",
            data={
                "candidate_count": len(search_results),
                "candidate_scheme_ids": [
                    result.scheme.scheme_id for result in search_results
                ],
            },
        )

        if not search_results:
            follow_up_questions = []

            if profile.is_student is not False:
                follow_up_questions = self._questions_from_missing_fields(basic_missing_fields)

            if follow_up_questions:
                final_message = self._build_follow_up_message(
                    follow_up_questions=follow_up_questions,
                    privacy_warnings=extraction.privacy_warnings,
                )

                add_step(
                    thought="No candidate schemes were found yet because important search details are missing.",
                    action=AgentAction.ask_follow_up,
                    observation=f"Prepared {len(follow_up_questions)} follow-up question(s).",
                    data={"follow_up_questions": follow_up_questions},
                )

                return AgentRunResult(
                    profile=profile,
                    search_results=[],
                    eligibility_results=[],
                    ranked_results=[],
                    steps=steps,
                    needs_follow_up=True,
                    follow_up_questions=follow_up_questions,
                    final_message=final_message,
                )

            final_message = self._build_no_verified_match_message(
                privacy_warnings=extraction.privacy_warnings,
            )

            add_step(
                thought="No candidate schemes were found, so I should show a no-match response.",
                action=AgentAction.final_response,
                observation="Created a no-match response.",
                data={"final_message": final_message},
            )

            return AgentRunResult(
                profile=profile,
                search_results=[],
                eligibility_results=[],
                ranked_results=[],
                steps=steps,
                needs_follow_up=False,
                follow_up_questions=[],
                final_message=final_message,
            )

        eligibility_results: list[EligibilityResult] = []

        # Step 3: run rule-based checks only for the strongest candidates.
        for search_result in search_results[: self.max_candidate_checks]:
            eligibility = check_eligibility_for_scheme(
                profile=profile,
                scheme=search_result.scheme,
            )
            eligibility_results.append(eligibility)

        add_step(
            thought="Candidate schemes need rule-based eligibility and readiness checks.",
            action=AgentAction.check_eligibility,
            observation=(
                "Checked eligibility/readiness for "
                f"{len(eligibility_results)} candidate scheme(s)."
            ),
            data={
                "eligibility_statuses": [
                    {
                        "scheme_id": result.scheme_id,
                        "status": result.status.value,
                        "confidence": result.confidence,
                    }
                    for result in eligibility_results
                ]
            },
        )

        # Step 4: combine retrieval relevance and eligibility status.
        ranked_results = rank_scheme_results(
            search_results=search_results,
            eligibility_results=eligibility_results,
        )
        # Do not show hard-blocked schemes as recommendations in the UI.
        actionable_ranked_results = self._actionable_ranked_results(ranked_results)

        add_step(
            thought="Multiple candidate schemes need ranking before creating guidance.",
            action=AgentAction.rank_results,
            observation=f"Ranked {len(ranked_results)} scheme result(s).",
            data={
                "ranked_results": [
                    {
                        "scheme_id": ranked.search_result.scheme.scheme_id,
                        "rank_score": ranked.rank_score,
                        "recommendation_label": ranked.recommendation_label.value,
                        "eligibility_status": ranked.eligibility_result.status.value,
                    }
                    for ranked in ranked_results
                ]
            },
        )

        # Step 5: ask for missing details before showing scheme analysis.
        follow_up_questions = self._build_follow_up_questions(actionable_ranked_results)
        needs_follow_up = len(follow_up_questions) > 0

        if needs_follow_up:
            final_message = self._build_follow_up_message(
                follow_up_questions=follow_up_questions,
                privacy_warnings=extraction.privacy_warnings,
            )

            add_step(
                thought="Some important eligibility details are missing, so I should ask focused follow-up questions.",
                action=AgentAction.ask_follow_up,
                observation=f"Prepared {len(follow_up_questions)} follow-up question(s).",
                data={"follow_up_questions": follow_up_questions},
            )
        elif not actionable_ranked_results:
            final_message = self._build_no_verified_match_message(
                privacy_warnings=extraction.privacy_warnings,
            )

            add_step(
                thought="Every checked candidate has a blocking issue, so I should show a no-match response.",
                action=AgentAction.final_response,
                observation="Created a no-match response.",
                data={"final_message": final_message},
            )

            return AgentRunResult(
                profile=profile,
                search_results=[],
                eligibility_results=[],
                ranked_results=[],
                steps=steps,
                needs_follow_up=False,
                follow_up_questions=[],
                final_message=final_message,
            )
        else:
            final_message = self._build_final_guidance_message(
                ranked_results=actionable_ranked_results,
                privacy_warnings=extraction.privacy_warnings,
            )

            add_step(
                thought="Enough information is available to give cautious readiness guidance.",
                action=AgentAction.final_response,
                observation="Created final guidance message.",
                data={"final_message": final_message},
            )

        return AgentRunResult(
            profile=profile,
            search_results=search_results,
            eligibility_results=eligibility_results,
            ranked_results=actionable_ranked_results,
            steps=steps,
            needs_follow_up=needs_follow_up,
            follow_up_questions=follow_up_questions,
            final_message=final_message,
        )
        
    def _actionable_ranked_results(
        self,
        ranked_results: list[RankedSchemeResult],
    ) -> list[RankedSchemeResult]:
        """Remove schemes with clear blocking failures from final recommendations."""
        return [
            ranked
            for ranked in ranked_results
            if ranked.eligibility_result.status != MatchStatus.not_a_match
        ]

    def _build_follow_up_questions(
        self,
        ranked_results: list[RankedSchemeResult],
    ) -> list[str]:
        """Build up to three follow-up questions from missing eligibility data.

        Questions are generated from the underlying EligibilityRule.field_name
        whenever possible. This makes follow-ups work for new schemes as long as
        their rules point to fields in CitizenProfile.
        """
        questions: list[str] = []

        for ranked in ranked_results:
            if ranked.eligibility_result.status not in {
                MatchStatus.possible_match,
                MatchStatus.not_enough_information,
            }:
                continue

            missing_items = ranked.eligibility_result.missing_information
            # Ask the broad condition first. Example: ask whether disability
            # applies before asking for disability percentage.
            has_missing_gender_condition = any(
                "gender" in item.lower() or "girl-student" in item.lower()
                for item in missing_items
            )
            has_missing_disability_status = any(
                "disability status" in item.lower() or "specially-abled" in item.lower()
                for item in missing_items
            )

            for missing_item in missing_items:
                normalized_missing_item = missing_item.lower()

                if has_missing_gender_condition and "girl children" in normalized_missing_item:
                    continue

                if has_missing_disability_status and "disability percentage" in normalized_missing_item:
                    continue

                rule = self._rule_for_missing_item(
                    scheme=ranked.search_result.scheme,
                    missing_item=missing_item,
                )
                question = self._question_for_rule(rule) if rule else None

                if question is None:
                    question = self._question_for_missing_item(missing_item)

                if question and question not in questions:
                    questions.append(question)

                if len(questions) == 3:
                    return questions

        return questions

    def _rule_for_missing_item(
        self,
        scheme: Scheme,
        missing_item: str,
    ) -> Optional[EligibilityRule]:
        """Find the EligibilityRule that produced a missing/failure message."""
        for rule in scheme.eligibility_rules:
            if missing_item in {rule.missing_message, rule.failed_reason}:
                return rule

        return None

    def _question_for_rule(self, rule: EligibilityRule) -> Optional[str]:
        """Create a follow-up question from a machine-readable rule."""
        mapped_question = FIELD_QUESTION_MAP.get(rule.field_name)

        if mapped_question:
            return mapped_question

        label = _field_label(rule.field_name)

        if rule.operator in {RuleOperator.is_true, RuleOperator.is_false}:
            return f"Can you confirm whether {label} applies?"

        if rule.operator in {RuleOperator.max_value, RuleOperator.min_value}:
            return f"What is your {label}?"

        if rule.operator == RuleOperator.in_list and rule.expected_values:
            options = ", ".join(str(value) for value in rule.expected_values[:5])
            return f"What is your {label}? Accepted values include: {options}."

        if rule.operator == RuleOperator.equals and rule.expected_value is not None:
            return f"What is your {label}?"

        if rule.operator == RuleOperator.contains_any:
            return f"Please provide your {label}."

        return f"Please provide your {label}."

    def _question_for_missing_item(self, missing_item: str) -> Optional[str]:
        """Fallback question builder for legacy/custom missing-message text."""
        normalized = missing_item.lower()

        if "gender" in normalized:
            return (
                "Does the girl-student condition apply to you for this scheme? "
                "You may answer Yes, No, or Prefer not to say."
            )

        if "student status" in normalized:
            return "Are you currently a student?"

        if "education level" in normalized:
            return (
                "What is your current education level? "
                "For example: school, undergraduate, postgraduate, diploma, or vocational."
            )

        if "course name" in normalized or "technical degree" in normalized:
            return (
                "What course are you studying? "
                "For example: B.Tech, B.E., diploma, BA, BSc, or another course."
            )

        if "admission type" in normalized:
            return (
                "Were you admitted into the first year normally, "
                "or into the second year through lateral entry?"
            )

        if "aicte" in normalized:
            return "Is your institution AICTE-approved?"

        if "annual family income" in normalized:
            return "What is your approximate annual family income in INR?"

        if "income certificate" in normalized:
            return "Do you have a valid income certificate issued by your State or UT Government?"

        if "girl children" in normalized:
            return (
                "How many girl children are in your family? "
                "You may skip this if you are not comfortable sharing."
            )

        if "other scholarship" in normalized or "financial assistance" in normalized:
            return "Are you currently receiving any other scholarship or financial assistance?"

        if "application window" in normalized:
            return None
        
        if "disability percentage" in normalized:
            return (
                "What is your disability percentage as mentioned on your disability certificate? "
                "You may skip this if you are not comfortable sharing."
            )

        if "disability status" in normalized or "specially-abled" in normalized:
            return (
                "Does the specially-abled or disability condition apply to you for this scheme? "
                "You may answer Yes, No, or Prefer not to say."
            )
        return None

    def _questions_from_missing_fields(self, missing_fields: list[str]) -> list[str]:
        """Build basic profile questions when no scheme candidates are available."""
        questions: list[str] = []

        for field_name in missing_fields:
            question = FIELD_QUESTION_MAP.get(field_name)

            if question and question not in questions:
                questions.append(question)

        return questions[:3]

    def _build_no_scheme_message(
        self,
        missing_fields: list[str],
        privacy_warnings: list[str],
    ) -> str:
        """Legacy no-scheme message kept for compatibility with older flows."""
        message_parts: list[str] = []

        if privacy_warnings:
            message_parts.append(
                "Privacy note: please do not share sensitive identifiers."
            )

        message_parts.append(
            "I could not find a strong verified scheme match from the current local database."
        )

        follow_up_questions = self._questions_from_missing_fields(missing_fields)

        if follow_up_questions:
            message_parts.append("To search better, I need:")
            message_parts.extend(f"- {question}" for question in follow_up_questions)
        else:
            message_parts.append(
                "This may be because our current database has only a small number of verified schemes."
            )

        return "\n".join(message_parts)

    def _build_no_verified_match_message(
        self,
        privacy_warnings: list[str],
    ) -> str:
        """Message shown when no actionable verified candidate remains."""
        message_parts: list[str] = []

        if privacy_warnings:
            message_parts.append(
                "Privacy note: please do not share Aadhaar numbers, OTPs, bank account numbers, or certificate IDs."
            )

        message_parts.append(
            "I could not find a verified scheme match from the current local database based on the details provided."
        )
        message_parts.append(
            "You can try again with different or corrected details, or verify directly on official portals."
        )

        return "\n".join(message_parts)

    def _build_follow_up_message(
        self,
        follow_up_questions: list[str],
        privacy_warnings: list[str],
    ) -> str:
        """Message shown when the UI should ask questions before analysis."""
        message_parts: list[str] = []

        if privacy_warnings:
            message_parts.append(
                "Privacy note: please do not share Aadhaar numbers, OTPs, bank account numbers, or certificate IDs."
            )

        message_parts.append(
            "I need a little more information before I can show the best verified matches."
        )
        message_parts.append(
            "Please answer the questions below. You may skip any question you are not comfortable answering."
        )

        return "\n".join(message_parts)

    def _build_final_guidance_message(
        self,
        ranked_results: list[RankedSchemeResult],
        privacy_warnings: list[str],
    ) -> str:
        """Build the final user-facing guidance after enough information exists."""
        message_parts: list[str] = []

        if privacy_warnings:
            message_parts.append(
                "Privacy note: please do not share Aadhaar numbers, OTPs, bank account numbers, or certificate IDs."
            )

        if not ranked_results:
            return (
                "I could not rank any verified schemes from the current database. "
                "Please provide more details or verify directly on official portals."
            )

        message_parts.append(
            f"I checked {len(ranked_results)} verified scheme candidate(s) and ranked them below."
        )

        for index, ranked in enumerate(ranked_results[:3], start=1):
            scheme = ranked.search_result.scheme
            eligibility = ranked.eligibility_result
            status = eligibility.status

            message_parts.append("")
            message_parts.append(f"## {index}. {scheme.name}")
            message_parts.append(f"- Recommendation: {ranked.recommendation_label.value}")
            message_parts.append(f"- Eligibility status: {status.value}")
            message_parts.append(f"- Ranking score: {ranked.rank_score}")

            message_parts.append("")
            message_parts.append(eligibility.user_message)

            if eligibility.not_matched_reasons:
                message_parts.append("\nBlocking issue:")
                for reason in eligibility.not_matched_reasons:
                    message_parts.append(f"- {reason}")

            if eligibility.matched_reasons:
                if status == MatchStatus.not_a_match:
                    message_parts.append(
                        "\nOther checks that matched, but do not override the blocking issue:"
                    )
                else:
                    message_parts.append("\nWhy this may fit:")

                for reason in eligibility.matched_reasons:
                    message_parts.append(f"- {reason}")

            if eligibility.missing_information:
                message_parts.append("\nStill missing or uncertain:")
                for item in eligibility.missing_information:
                    message_parts.append(f"- {item}")

            if scheme.required_documents and status != MatchStatus.not_a_match:
                message_parts.append("\nDocuments to prepare:")
                for document in scheme.required_documents[:5]:
                    message_parts.append(f"- {document}")

            if scheme.application_window:
                if status == MatchStatus.not_a_match:
                    message_parts.append("\nApplication window for reference:")
                else:
                    message_parts.append("\nApplication window:")

                message_parts.append(f"- Status: {scheme.application_window.status.value}")
                message_parts.append(f"- Academic year: {scheme.application_window.academic_year}")
                message_parts.append(f"- Student deadline: {scheme.application_window.student_deadline}")

            message_parts.append("\nOfficial sources:")
            for source in scheme.sources:
                message_parts.append(
                    f"- {source.publisher}: {source.url}"
                )

        message_parts.append(
            "\nThis is readiness guidance, not final eligibility. Please verify on the official portal before applying."
        )

        return "\n".join(message_parts)
