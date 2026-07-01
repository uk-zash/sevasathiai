"""Evaluate one citizen profile against one scheme's eligibility rules."""

from app.models import (
    AdmissionType,
    ApplicationStatus,
    CitizenProfile,
    EducationLevel,
    EligibilityResult,
    Gender,
    MatchStatus,
    Scheme
)

from typing import Optional, List   
from app.rule_engine import check_scheme_with_rules

PRAGATI_DEGREE_SCHEME_ID = "aicte_pragati_degree"
PRAGATI_INCOME_LIMIT = 800000


def _normalize_text(value: Optional[str]) -> str:
    """Normalize optional text for simple keyword checks."""
    if value is None:
        return ""
    
    return value.strip().lower()

def _course_looks_technical_degree(course_name: Optional[str]) -> Optional[bool]:
    """Detect whether a course name resembles a technical degree.

    Returns None when the course is missing, so the caller can distinguish
    unknown information from a known non-technical course.
    """
    normalized_course = _normalize_text(course_name)

    if not normalized_course:
        return None
    
    technical_terms = [
        "b.tech",
        "btech",
        "b.e",
        "be",
        "engineering",
        "technology",
    ]
    
    return any(term in normalized_course for term in technical_terms)


def _build_user_message(
        scheme: Scheme, 
        status: MatchStatus,
        matched_reasons: List[str],
        missing_information: List[str],
        not_matched_reasons: List[str],
) -> str:
    """Create the short human-readable eligibility summary for one scheme."""
    if status == MatchStatus.likely_match:
        return (
            f"You appear to match the main readiness checks for {scheme.name} based on the information provided. "
            "This is not final eligibility. Please verify all details and apply only through the official portal."
        )

    if status == MatchStatus.possible_match:
        return (
            f"You may match {scheme.name}, but some important details are still missing or uncertain. "
            "Please verify the missing points before relying on this guidance."
        )

    if status == MatchStatus.not_enough_information:
        return (
            f"I do not have enough information to assess {scheme.name} yet. "
            "Please provide the missing details and verify everything on the official portal."
        )

    return (
        f"Based on the information provided, you do not appear to match {scheme.name}. "
        "Please verify on the official portal because scheme rules and user details can vary."
    )


def _decide_result(
    scheme: Scheme,
    matched_reasons: list[str],
    missing_information: list[str],
    not_matched_reasons: list[str],
) -> EligibilityResult:
    """Convert collected rule evidence into status, confidence, and message."""
    if not_matched_reasons:
        status = MatchStatus.not_a_match
        confidence = 0.8
    elif missing_information:
        if len(matched_reasons) >= 3:
            status = MatchStatus.possible_match
            confidence = 0.6
        else:
            status = MatchStatus.not_enough_information
            confidence = 0.35
    else:
        status = MatchStatus.likely_match
        confidence = 0.85

    user_message = _build_user_message(
        scheme=scheme,
        status=status,
        matched_reasons=matched_reasons,
        missing_information=missing_information,
        not_matched_reasons=not_matched_reasons,
    )

    return EligibilityResult(
        scheme_id=scheme.scheme_id,
        status=status,
        confidence=confidence,
        matched_reasons=matched_reasons,
        missing_information=missing_information,
        not_matched_reasons=not_matched_reasons,
        user_message=user_message,
    )


def _check_aicte_pragati_degree(profile: CitizenProfile, scheme: Scheme) -> EligibilityResult:
    """Legacy hard-coded checker kept for Pragati when no JSON rules exist.

    New schemes should prefer `scheme.eligibility_rules`, which are handled by
    the generic rule engine without adding scheme-specific Python code.
    """
    matched_reasons: list[str] = []
    missing_information: list[str] = []
    not_matched_reasons: list[str] = []

    if profile.gender == Gender.female:
        matched_reasons.append("The user shared female gender, matching the girl-student focus of the scheme.")
    elif profile.gender in {None, Gender.prefer_not_to_say}:
        missing_information.append("Gender is needed because this scheme is specifically for girl students.")
    else:
        not_matched_reasons.append("This scheme is specifically for girl students, but the user did not share female gender.")

    if profile.is_student is True:
        matched_reasons.append("The user is currently a student.")
    elif profile.is_student is False:
        not_matched_reasons.append("This scheme is for students, but the user is not currently a student.")
    else:
        missing_information.append("Student status is missing.")

    if profile.education_level == EducationLevel.undergraduate:
        matched_reasons.append("The user is at undergraduate level, which can match a degree-level scheme.")
    elif profile.education_level is None:
        missing_information.append("Education level is missing; this scheme is for degree-level study.")
    else:
        not_matched_reasons.append("This scheme is for degree-level technical study, but the user's education level does not appear to be undergraduate.")

    technical_course_check = _course_looks_technical_degree(profile.course_name)

    if technical_course_check is True:
        matched_reasons.append("The user's course appears to be technical or engineering-related.")
    elif technical_course_check is False:
        not_matched_reasons.append("The course name does not appear to be a technical degree course.")
    else:
        missing_information.append("Course name is missing; this scheme requires technical degree study.")

    if profile.admission_type in {
        AdmissionType.first_year_regular,
        AdmissionType.second_year_lateral_entry,
    }:
        matched_reasons.append("The admission type matches first-year regular admission or second-year lateral entry.")
    elif profile.admission_type in {None, AdmissionType.unknown}:
        missing_information.append("Admission type is missing; this scheme requires first-year degree admission or second-year lateral entry.")
    else:
        not_matched_reasons.append("The admission type does not match first-year regular admission or second-year lateral entry.")

    if profile.is_aicte_approved_institution is True:
        matched_reasons.append("The user says the institution is AICTE-approved.")
    elif profile.is_aicte_approved_institution is False:
        not_matched_reasons.append("This scheme requires an AICTE-approved institution, but the user says the institution is not AICTE-approved.")
    else:
        missing_information.append("AICTE approval status of the institution is missing.")

    if profile.annual_family_income is not None:
        if profile.annual_family_income <= PRAGATI_INCOME_LIMIT:
            matched_reasons.append("The user's family income is within the Rs. 8 lakh annual limit.")
        else:
            not_matched_reasons.append("The user's family income is above the Rs. 8 lakh annual limit.")
    else:
        missing_information.append("Annual family income is missing.")

    if profile.has_valid_income_certificate is True:
        matched_reasons.append("The user says they have a valid income certificate.")
    elif profile.has_valid_income_certificate is False:
        missing_information.append("A valid State/UT income certificate is needed for application readiness.")
    else:
        missing_information.append("Income certificate availability is unknown.")

    if profile.girl_children_in_family is not None:
        if profile.girl_children_in_family <= 2:
            matched_reasons.append("The number of girl children in the family is within the scheme limit.")
        else:
            not_matched_reasons.append("The scheme allows a maximum of two girl children per family.")
    else:
        missing_information.append("Number of girl children in the family is missing.")

    if profile.receiving_other_scholarship is False:
        matched_reasons.append("The user says they are not receiving another scholarship or financial assistance.")
    elif profile.receiving_other_scholarship is True:
        not_matched_reasons.append("The scheme does not allow receiving another scholarship or financial assistance during the course.")
    else:
        missing_information.append("Other scholarship or financial assistance status is missing.")

    if scheme.application_window and scheme.application_window.status == ApplicationStatus.open:
        matched_reasons.append("The application window is marked open in the verified scheme database.")
    elif scheme.application_window and scheme.application_window.status == ApplicationStatus.closed:
        not_matched_reasons.append("The application window is marked closed in the verified scheme database.")
    else:
        missing_information.append("Current application window status is unknown.")

    return _decide_result(
        scheme=scheme,
        matched_reasons=matched_reasons,
        missing_information=missing_information,
        not_matched_reasons=not_matched_reasons,
    )


def check_eligibility_for_scheme(profile: CitizenProfile, scheme: Scheme) -> EligibilityResult:
    """Choose the correct eligibility checker for a scheme."""
    # Generic JSON rules are the scalable path: adding a new scheme to
    # schemes.json should normally be enough for eligibility evaluation.
    if scheme.eligibility_rules:
        return check_scheme_with_rules(profile=profile, scheme=scheme)

    # Backward-compatible fallback for older seed data.
    if scheme.scheme_id == PRAGATI_DEGREE_SCHEME_ID:
        return _check_aicte_pragati_degree(profile=profile, scheme=scheme)

    return EligibilityResult(
        scheme_id=scheme.scheme_id,
        status=MatchStatus.not_enough_information,
        confidence=0.2,
        matched_reasons=[],
        missing_information=[
            "No rule-based eligibility checker has been implemented for this scheme yet."
        ],
        not_matched_reasons=[],
        user_message=(
            "This scheme exists in the verified database, but a rule-based eligibility checker "
            "has not been implemented for it yet. Please verify directly on the official portal."
        ),
    )
