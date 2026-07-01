"""Deterministic parser for Streamlit follow-up answers.

The LLM still sees follow-up answers, but this module immediately extracts
structured values from known UI questions so the profile updates reliably after
each form submit.
"""

import re
from typing import Optional

from app.models import (
    AdmissionType,
    CitizenProfile,
    EducationLevel,
    Gender,
    InstitutionType,
    SocialCategory,
)


def _normalize_text(value: str) -> str:
    """Lowercase and trim user-entered answer text."""
    return value.strip().lower()


def _answer_is_yes(answer: str) -> bool:
    """Return true for radio answers that begin with Yes."""
    normalized = _normalize_text(answer)
    return normalized.startswith("yes")


def _answer_is_no(answer: str) -> bool:
    """Return true for radio answers that begin with No."""
    normalized = _normalize_text(answer)
    return normalized.startswith("no")


def _answer_is_unknown(answer: str) -> bool:
    """Return true when the user skipped, declined, or does not know."""
    normalized = _normalize_text(answer)
    return (
        "do not know" in normalized
        or "don't know" in normalized
        or "prefer not" in normalized
        or "select an answer" in normalized
        or "skip" in normalized
    )


def _parse_number(value: str) -> Optional[float]:
    """Parse numeric answers, including Indian lakh/lac shorthand."""
    normalized = _normalize_text(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", normalized)

    if match is None:
        return None

    number = float(match.group())

    if "lakh" in normalized or "lac" in normalized:
        return number * 100000

    return number


def _parse_int(value: str) -> Optional[int]:
    """Parse an integer from a free-text answer."""
    number = _parse_number(value)

    if number is None:
        return None

    return int(number)


def _education_level_from_answer(answer: str) -> Optional[EducationLevel]:
    """Map UI education-level labels to EducationLevel enum values."""
    normalized = _normalize_text(answer)

    if "undergraduate" in normalized:
        return EducationLevel.undergraduate

    if "postgraduate" in normalized:
        return EducationLevel.postgraduate

    if "diploma" in normalized:
        return EducationLevel.diploma

    if "vocational" in normalized:
        return EducationLevel.vocational

    if "school" in normalized:
        return EducationLevel.school

    if "not applicable" in normalized:
        return EducationLevel.not_applicable

    return None


def _admission_type_from_answer(answer: str) -> Optional[AdmissionType]:
    """Map admission follow-up answers to AdmissionType enum values."""
    normalized = _normalize_text(answer)

    if "first year" in normalized:
        return AdmissionType.first_year_regular

    if "lateral" in normalized or "second year" in normalized:
        return AdmissionType.second_year_lateral_entry

    if "continuing" in normalized or "later year" in normalized:
        return AdmissionType.continuing_student

    if "do not know" in normalized or "don't know" in normalized:
        return AdmissionType.unknown

    return None


def _institution_type_from_answer(answer: str) -> Optional[InstitutionType]:
    """Map institution-type answers to InstitutionType enum values."""
    normalized = _normalize_text(answer)

    if "government" in normalized:
        return InstitutionType.government

    if "private" in normalized:
        return InstitutionType.private

    if "aided" in normalized:
        return InstitutionType.aided

    if "open" in normalized:
        return InstitutionType.open_university

    if "do not know" in normalized or "don't know" in normalized:
        return InstitutionType.unknown

    return None


def _social_category_from_answer(answer: str) -> Optional[SocialCategory]:
    """Map social-category answers to SocialCategory enum values."""
    normalized = _normalize_text(answer)

    if "prefer not" in normalized:
        return SocialCategory.prefer_not_to_say

    if "general" in normalized:
        return SocialCategory.general

    if re.search(r"\bsc\b", normalized):
        return SocialCategory.sc

    if re.search(r"\bst\b", normalized):
        return SocialCategory.st

    if "obc" in normalized:
        return SocialCategory.obc

    if "ews" in normalized:
        return SocialCategory.ews

    if "unknown" in normalized or "do not know" in normalized or "don't know" in normalized:
        return SocialCategory.unknown

    return None


def profile_update_from_follow_up_answers(
    question_answer_pairs: list[tuple[str, str]],
) -> CitizenProfile:
    """Build a partial CitizenProfile from follow-up question/answer pairs.

    Args:
        question_answer_pairs: Tuples of the displayed follow-up question and
            the user's selected/typed answer.

    Returns:
        A partial CitizenProfile containing only fields confidently parsed from
        the answers. The caller merges it into the existing profile.
    """
    update_data = {}

    for question, answer in question_answer_pairs:
        clean_answer = answer.strip()

        if not clean_answer:
            continue

        normalized_question = _normalize_text(question)
        normalized_answer = _normalize_text(clean_answer)

        # The parser keys off question wording because short answers like
        # "Yes" or "45%" need the question to identify the target field.
        if (
            "which indian state" in normalized_question
            or "which state" in normalized_question
            or "union territory do you live" in normalized_question
        ):
            if not _answer_is_unknown(clean_answer):
                update_data["state"] = clean_answer
            continue

        if "district" in normalized_question:
            if not _answer_is_unknown(clean_answer):
                update_data["district"] = clean_answer
            continue

        if re.search(r"\bage\b", normalized_question):
            age = _parse_int(clean_answer)

            if age is not None:
                update_data["age"] = age
            continue

        if "disability percentage" in normalized_question:
            disability_percentage = _parse_number(clean_answer)

            if disability_percentage is not None:
                update_data["disability_percentage"] = disability_percentage
                update_data["has_disability"] = True
            continue

        if (
            "disability condition" in normalized_question
            or "disability status" in normalized_question
            or "specially-abled" in normalized_question
        ):
            if _answer_is_yes(clean_answer):
                update_data["has_disability"] = True
            elif _answer_is_no(clean_answer):
                update_data["has_disability"] = False
            continue

        if "girl-student condition" in normalized_question or "gender" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["gender"] = Gender.female
            elif _answer_is_no(clean_answer):
                update_data["gender"] = Gender.other
            elif "prefer not" in normalized_answer:
                update_data["gender"] = Gender.prefer_not_to_say
            continue

        if "currently a student" in normalized_question or "student status" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["is_student"] = True
            elif _answer_is_no(clean_answer):
                update_data["is_student"] = False
            continue

        if "education level" in normalized_question:
            education_level = _education_level_from_answer(clean_answer)

            if education_level is not None:
                update_data["education_level"] = education_level
            continue

        if "first year" in normalized_question or "lateral entry" in normalized_question:
            admission_type = _admission_type_from_answer(clean_answer)

            if admission_type is not None:
                update_data["admission_type"] = admission_type
            continue

        if "institution type" in normalized_question or "type of institution" in normalized_question:
            institution_type = _institution_type_from_answer(clean_answer)

            if institution_type is not None:
                update_data["institution_type"] = institution_type
            continue

        if "course" in normalized_question:
            if not _answer_is_unknown(clean_answer):
                update_data["course_name"] = clean_answer
            continue

        if "aicte" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["is_aicte_approved_institution"] = True
            elif _answer_is_no(clean_answer):
                update_data["is_aicte_approved_institution"] = False
            continue

        if "family income" in normalized_question:
            income = _parse_number(clean_answer)

            if income is not None:
                update_data["annual_family_income"] = income
            continue

        if "income certificate" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["has_valid_income_certificate"] = True
            elif _answer_is_no(clean_answer):
                update_data["has_valid_income_certificate"] = False
            continue

        if "girl children" in normalized_question:
            girl_children = _parse_int(clean_answer)

            if girl_children is not None:
                update_data["girl_children_in_family"] = girl_children
            continue

        if "other scholarship" in normalized_question or "financial assistance" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["receiving_other_scholarship"] = True
            elif _answer_is_no(clean_answer):
                update_data["receiving_other_scholarship"] = False
            continue

        if "minority" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["minority_status"] = True
            elif _answer_is_no(clean_answer):
                update_data["minority_status"] = False
            continue

        if "social category" in normalized_question:
            social_category = _social_category_from_answer(clean_answer)

            if social_category is not None:
                update_data["social_category"] = social_category
            continue

        if "category-based" in normalized_question or "category based" in normalized_question:
            if _answer_is_yes(clean_answer):
                update_data["wants_category_based_schemes"] = True
            elif _answer_is_no(clean_answer):
                update_data["wants_category_based_schemes"] = False
            continue

        if "disability" in normalized_answer:
            disability_percentage = _parse_number(clean_answer)

            if disability_percentage is not None:
                update_data["has_disability"] = True
                update_data["disability_percentage"] = disability_percentage

        if "female" in normalized_answer or "girl" in normalized_answer:
            update_data["gender"] = Gender.female

    return CitizenProfile(**update_data)
