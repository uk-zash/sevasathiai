"""Tests for deterministic parsing of follow-up question/answer pairs."""

from app.follow_up_parser import profile_update_from_follow_up_answers
from app.models import AdmissionType, EducationLevel, Gender


def test_parser_updates_disability_status_from_radio_answer() -> None:
    update = profile_update_from_follow_up_answers(
        [
            (
                "Does the specially-abled or disability condition apply to you for this scheme?",
                "Yes, I have a disability",
            )
        ]
    )

    assert update.has_disability is True


def test_parser_updates_disability_percentage_from_text_answer() -> None:
    update = profile_update_from_follow_up_answers(
        [
            (
                "What is your disability percentage as mentioned on your disability certificate?",
                "45%",
            )
        ]
    )

    assert update.has_disability is True
    assert update.disability_percentage == 45


def test_parser_updates_girl_student_condition_from_radio_answer() -> None:
    update = profile_update_from_follow_up_answers(
        [
            (
                "Does the girl-student condition apply to you for this scheme?",
                "Yes, I am a girl/female student for this scheme",
            )
        ]
    )

    assert update.gender == Gender.female


def test_parser_updates_common_scholarship_follow_up_fields() -> None:
    # Short answers are interpreted using the question text, which mirrors how
    # the Streamlit follow-up form sends data back into the agent.
    update = profile_update_from_follow_up_answers(
        [
            ("What is your current education level?", "Undergraduate"),
            ("Were you admitted into the first year normally?", "First year regular admission"),
            ("Do you have a valid income certificate?", "Yes, I have a valid income certificate"),
            ("What is your approximate annual family income in INR?", "2.5 lakh"),
        ]
    )

    assert update.education_level == EducationLevel.undergraduate
    assert update.admission_type == AdmissionType.first_year_regular
    assert update.has_valid_income_certificate is True
    assert update.annual_family_income == 250000


def test_parser_keeps_b_tech_course_and_first_year_answer() -> None:
    update = profile_update_from_follow_up_answers(
        [
            ("What course are you studying?", "B Tech"),
            (
                "Were you admitted into the first year normally, or into the second year through lateral entry?",
                "First year",
            ),
        ]
    )

    assert update.course_name == "B Tech"
    assert update.admission_type == AdmissionType.first_year_regular


def test_parser_ignores_declined_structured_follow_up_answers() -> None:
    update = profile_update_from_follow_up_answers(
        [
            ("Which Indian state or union territory do you live in?", "Prefer not to say"),
            ("What course are you studying?", "Skip this question"),
            (
                "What is your disability percentage as mentioned on your disability certificate?",
                "Prefer not to say",
            ),
        ]
    )

    assert update.state is None
    assert update.course_name is None
    assert update.disability_percentage is None
