from app.eligibility_checker import  check_eligibility_for_scheme
from app.models import (
    AgentAction,
    AgentRunResult,
    AgentStep,
    CitizenProfile,
    EligibilityResult,
    MatchStatus,
    RankedSchemeResult,
    RecommendationLabel,
    SchemeSearchResult,
)

from app.ranking import rank_scheme_results
from app.profile_merge import get_basic_missing_profile_fields, merge_citizen_profiles

from app.profile_extractor import extract_profile_from_text
from app.scheme_search import search_schemes_for_profile
from typing import Optional

class SevaSathiTAORAgent:
    def __init__(self , max_candidate_checks: int = 3) -> None:
        if max_candidate_checks < 1 :
            raise ValueError("max_candidate_checks must be atleast 1")
        
        self.max_candidate_checks = max_candidate_checks

    
    def run(
        self,
        user_text: str,
        existing_profile: Optional[CitizenProfile] = None
    ) -> AgentRunResult:
        steps: list[AgentStep] = []
        step_number = 1

        def add_step(
            thought: str,
            action: AgentAction,
            observation: str,
            data: Optional[dict] = None, 
        ) -> None:
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

        search_results = search_schemes_for_profile(profile)

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
            final_message = self._build_no_scheme_message(
                missing_fields=basic_missing_fields,
                privacy_warnings=extraction.privacy_warnings,
            )

            add_step(
                thought="No candidate schemes were found, so I should explain what information may be needed next.",
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
                needs_follow_up=bool(basic_missing_fields),
                follow_up_questions=self._questions_from_missing_fields(basic_missing_fields),
                final_message=final_message,
            )

        eligibility_results: list[EligibilityResult] = []

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

        ranked_results = rank_scheme_results(
            search_results=search_results,
            eligibility_results=eligibility_results,
        )

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

        follow_up_questions = self._build_follow_up_questions(ranked_results)
        needs_follow_up = len(follow_up_questions) > 0

        if needs_follow_up:
            final_message = self._build_follow_up_message(
                ranked_results=ranked_results,
                follow_up_questions=follow_up_questions,
                privacy_warnings=extraction.privacy_warnings,
            )

            add_step(
                thought="Some important eligibility details are missing, so I should ask focused follow-up questions.",
                action=AgentAction.ask_follow_up,
                observation=f"Prepared {len(follow_up_questions)} follow-up question(s).",
                data={"follow_up_questions": follow_up_questions},
            )
        else:
            final_message = self._build_final_guidance_message(
                ranked_results=ranked_results,
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
            ranked_results=ranked_results,
            steps=steps,
            needs_follow_up=needs_follow_up,
            follow_up_questions=follow_up_questions,
            final_message=final_message,
        )
        

    def _build_follow_up_questions(
        self,
        ranked_results: list[RankedSchemeResult],
    ) -> list[str]:
        if any(
            ranked.eligibility_result.status == MatchStatus.likely_match
            for ranked in ranked_results
        ):
            return []

        top_actionable_result: RankedSchemeResult | None = None

        for ranked in ranked_results:
            if ranked.eligibility_result.status in {
                MatchStatus.possible_match,
                MatchStatus.not_enough_information,
            }:
                top_actionable_result = ranked
                break

        if top_actionable_result is None:
            return []

        questions: list[str] = []

        for missing_item in top_actionable_result.eligibility_result.missing_information:
            question = self._question_for_missing_item(missing_item)

            if question and question not in questions:
                questions.append(question)

        return questions[:3]

    def _question_for_missing_item(self, missing_item: str) -> Optional[str]:
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
            return "Please verify the current application window on the official portal before applying."
        
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
        field_question_map = {
            "state": "Which Indian state or union territory do you live in?",
            "age": "What is your age?",
            "is_student": "Are you currently a student?",
            "education_level": "What is your current education level?",
            "course_name": "What course or class are you studying?",
            "annual_family_income": "What is your approximate annual family income in INR?",
        }

        questions: list[str] = []

        for field_name in missing_fields:
            question = field_question_map.get(field_name)

            if question and question not in questions:
                questions.append(question)

        return questions[:3]

    def _build_no_scheme_message(
        self,
        missing_fields: list[str],
        privacy_warnings: list[str],
    ) -> str:
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

    def _build_follow_up_message(
        self,
        ranked_results: list[RankedSchemeResult],
        follow_up_questions: list[str],
        privacy_warnings: list[str],
    ) -> str:
        message_parts: list[str] = []

        if privacy_warnings:
            message_parts.append(
                "Privacy note: please do not share Aadhaar numbers, OTPs, bank account numbers, or certificate IDs."
            )

        top_ranked = ranked_results[0]
        best_scheme_name = top_ranked.search_result.scheme.name
        best_result = top_ranked.eligibility_result

        message_parts.append(
            f"I found a possible verified scheme match: {best_scheme_name}."
        )

        message_parts.append(
            f"Current recommendation level: {top_ranked.recommendation_label.value}."
        )

        message_parts.append(
            "I cannot give stronger readiness guidance yet because some important details are missing or uncertain."
        )

        if best_result.matched_reasons:
            message_parts.append("\nWhat already seems to match:")
            for reason in best_result.matched_reasons[:5]:
                message_parts.append(f"- {reason}")

        if best_result.missing_information:
            message_parts.append("\nWhat still needs to be clarified:")
            for item in best_result.missing_information[:5]:
                message_parts.append(f"- {item}")

        if len(ranked_results) > 1:
            message_parts.append("\nOther schemes checked:")
            for ranked in ranked_results[1:3]:
                scheme = ranked.search_result.scheme
                message_parts.append(
                    f"- {scheme.name}: {ranked.recommendation_label.value}, "
                    f"status {ranked.eligibility_result.status.value}"
                )

        message_parts.append(
            "\nPlease answer the follow-up questions shown in the form. "
            "You may skip any question you are not comfortable answering."
        )

        message_parts.append(
            "\nPlease verify all final details on the official portal before applying."
        )

        return "\n".join(message_parts)

    def _build_final_guidance_message(
        self,
        ranked_results: list[RankedSchemeResult],
        privacy_warnings: list[str],
    ) -> str:
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