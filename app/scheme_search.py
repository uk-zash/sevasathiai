from app.models import (
    ApplicationStatus,
    CitizenProfile,
    EducationLevel,
    Gender,
    Scheme,
    SchemeSearchResult,
)

from typing import Optional, List

from app.scheme_loader import load_schemes


def _normalize_text(value: Optional[str]) -> Scheme:
    if value is None:
        return ""
    
    return value.strip().lower()



def _build_scheme_text(scheme: Scheme) -> str:
    parts: list[str] = [
        scheme.name,
        scheme.summary,
        scheme.category.value,
        scheme.government_level.value
    ]

    parts.extend(scheme.target_groups)
    parts.extend(scheme.benefits)
    parts.extend(scheme.required_documents)
    parts.extend(scheme.eligibility_text)

    return " ".join(parts).lower()



def _is_girl_focused_scheme(scheme_text: str) -> bool:
    girl_terms = ["girl", "female", "women", "woman"]
    return any(term in scheme_text for term in girl_terms)
    

def _is_student_focused_scheme(scheme_text: str) -> bool:
    student_terms = ["student", "scholarship", "education", "course", "institution"]
    return any(term in scheme_text for term in student_terms)


def _is_technical_degree_scheme(scheme_text: str) -> bool:
    technical_terms = ["technical", "degree", "aicte", "engineering"]
    return any(term in scheme_text for term in technical_terms)




def score_scheme_for_profile(profile: CitizenProfile, scheme: Scheme) -> SchemeSearchResult:
    score = 0.0
    matched_reasons: list[str] = []
    possible_concerns: list[str] = []

    scheme_text = _build_scheme_text(scheme)

    user_state = _normalize_text(profile.state)
    scheme_state = _normalize_text(scheme.state)

    if scheme_state and user_state and scheme_state != user_state:
        return SchemeSearchResult(
            scheme=scheme,
            score=0.0,
            matched_reasons=[],
            possible_concerns=[
                f"This scheme is for {scheme.state}, but the user's state is {profile.state}."
            ],
        )

    if scheme.state is None:
        score += 0.20
        matched_reasons.append("The scheme is not limited to one state in our database.")
    elif user_state and scheme_state == user_state:
        score += 0.25
        matched_reasons.append(f"The scheme applies to the user's state: {profile.state}.")
    else:
        possible_concerns.append("User state is missing, so state-level relevance cannot be fully checked.")

    is_student_focused = _is_student_focused_scheme(scheme_text)

    if is_student_focused and profile.is_student is False:
        return SchemeSearchResult(
            scheme=scheme,
            score=0.0,
            matched_reasons=[],
            possible_concerns=[
                "This scheme appears student-focused, but the user is not currently a student."
            ],
        )

    if is_student_focused and profile.is_student is True:
        score += 0.20
        matched_reasons.append("The user is a student and the scheme is student-focused.")
    elif is_student_focused and profile.is_student is None:
        possible_concerns.append("The scheme is student-focused, but student status is missing.")

    if _is_girl_focused_scheme(scheme_text):
        if profile.gender == Gender.female:
            score += 0.20
            matched_reasons.append("The scheme is girl/female-focused and the user shared female gender.")
        elif profile.gender is None:
            possible_concerns.append("The scheme may be girl/female-focused, but gender is missing.")
        else:
            possible_concerns.append("The scheme may be girl/female-focused, but the user did not share female gender.")

    if _is_technical_degree_scheme(scheme_text):
        if profile.education_level == EducationLevel.undergraduate:
            score += 0.10
            matched_reasons.append("The user appears to be at undergraduate level and the scheme mentions degree study.")
        elif profile.education_level is None:
            possible_concerns.append("The scheme may require degree-level study, but education level is missing.")

        course_name = _normalize_text(profile.course_name)

        if any(term in course_name for term in ["b.tech", "btech", "engineering"]):
            score += 0.10
            matched_reasons.append("The user's course looks technical or engineering-related.")
        elif not course_name:
            possible_concerns.append("The scheme may require a technical course, but course name is missing.")

    if "income" in scheme_text:
        if profile.annual_family_income is not None:
            score += 0.10
            matched_reasons.append("The user provided family income, which is needed for this scheme.")
        else:
            possible_concerns.append("The scheme appears income-based, but family income is missing.")

    if scheme.application_window and scheme.application_window.status == ApplicationStatus.open:
        score += 0.05
        matched_reasons.append("The scheme application window is marked open in our verified database.")

    final_score = min(score, 1.0)

    return SchemeSearchResult(
        scheme=scheme,
        score=round(final_score, 2),
        matched_reasons=matched_reasons,
        possible_concerns=possible_concerns,
    )


def search_schemes_for_profile(
    profile: CitizenProfile,
    schemes: Optional[List[Scheme]] = None,
    min_score: float = 0.25,
) -> list[SchemeSearchResult]:
    if schemes is None:
        schemes = load_schemes()

    results = [
        score_scheme_for_profile(profile=profile, scheme=scheme)
        for scheme in schemes
    ]

    filtered_results = [
        result
        for result in results
        if result.score >= min_score
    ]

    return sorted(filtered_results, key=lambda result: result.score, reverse=True)