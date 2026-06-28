from app.models import (
    AdmissionType,
    CitizenProfile,
    EducationLevel,
    Gender,
    SocialCategory,
)
from app.profile_merge import merge_citizen_profiles


def test_merge_keeps_existing_values_when_update_has_missing_fields() -> None:
    existing_profile = CitizenProfile(
        age=21,
        state="Maharashtra",
        gender=Gender.female,
        is_student=True,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        annual_family_income=180000,
    )

    update = CitizenProfile(
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        has_valid_income_certificate=True,
        girl_children_in_family=2,
        receiving_other_scholarship=False,
    )

    merged = merge_citizen_profiles(
        existing_profile=existing_profile,
        update=update,
    )

    assert merged.age == 21
    assert merged.state == "Maharashtra"
    assert merged.gender == Gender.female
    assert merged.course_name == "B.Tech"
    assert merged.annual_family_income == 180000

    assert merged.admission_type == AdmissionType.first_year_regular
    assert merged.is_aicte_approved_institution is True
    assert merged.has_valid_income_certificate is True
    assert merged.girl_children_in_family == 2
    assert merged.receiving_other_scholarship is False


def test_merge_respects_prefer_not_to_say_for_category() -> None:
    existing_profile = CitizenProfile(
        state="Maharashtra",
        wants_category_based_schemes=True,
    )

    update = CitizenProfile(
        social_category=SocialCategory.prefer_not_to_say,
    )

    merged = merge_citizen_profiles(
        existing_profile=existing_profile,
        update=update,
    )

    assert merged.social_category == SocialCategory.prefer_not_to_say
    assert merged.wants_category_based_schemes is False