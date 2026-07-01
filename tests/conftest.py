"""Shared pytest fixtures for SevaSathi test cases."""

import pytest

from app.models import (
    AdmissionType,
    CitizenProfile,
    EducationLevel,
    Gender,
    InstitutionType,
    SocialCategory,
)


@pytest.fixture
def full_pragati_profile() -> CitizenProfile:
    """Return a complete profile that should satisfy the Pragati degree scheme."""
    return CitizenProfile(
        age=21,
        state="Maharashtra",
        district=None,
        gender=Gender.female,
        is_student=True,
        education_level=EducationLevel.undergraduate,
        course_name="B.Tech",
        institution_type=InstitutionType.private,
        admission_type=AdmissionType.first_year_regular,
        is_aicte_approved_institution=True,
        annual_family_income=180000,
        has_valid_income_certificate=True,
        girl_children_in_family=2,
        receiving_other_scholarship=False,
        social_category=SocialCategory.prefer_not_to_say,
        has_disability=None,
        minority_status=None,
        wants_category_based_schemes=False,
    )
