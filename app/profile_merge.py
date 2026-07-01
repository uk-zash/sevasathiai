"""Utilities for merging profile details across initial and follow-up answers."""

from typing import Optional

from app.models import CitizenProfile, SocialCategory

# These are the minimum useful fields for a broad first-pass scheme search.
IMPORTANT_BASIC_FIELDS = [
    "state",
    "is_student",
    "education_level",
    "course_name",
    "annual_family_income",
]

def merge_citizen_profiles(
    existing_profile: Optional[CitizenProfile],
    update: CitizenProfile,
) -> CitizenProfile:
    """Merge a new partial profile into the profile already stored in session.

    Args:
        existing_profile: Profile collected from earlier user messages, if any.
        update: Newly extracted profile values from the latest user/follow-up text.

    Returns:
        A CitizenProfile where explicit new answers overwrite old values, while
        missing values from the latest extraction do not erase known data.
    """
    if existing_profile is None:
        return update

    merged_data = existing_profile.model_dump()
    update_data = update.model_dump()

    for field_name, value in update_data.items():
        # Category-based scheme preference has special semantics below because
        # "prefer not to say" should actively turn that targeting off.
        if field_name == "wants_category_based_schemes":
            continue

        if value is not None:
            merged_data[field_name] = value

    # Once the user explicitly asks for category-based schemes, keep that intent
    # unless they later choose prefer_not_to_say for social category.
    if update.wants_category_based_schemes is True:
        merged_data["wants_category_based_schemes"] = True

    if update.social_category == SocialCategory.prefer_not_to_say:
        merged_data["wants_category_based_schemes"] = False

    return CitizenProfile.model_validate(merged_data)

def get_basic_missing_profile_fields(profile: CitizenProfile) -> list[str]:
    """Return important broad-search fields that are still absent."""
    missing_fields: list[str] = []

    for field_name in IMPORTANT_BASIC_FIELDS:
        value = getattr(profile, field_name)

        if value is None:
            missing_fields.append(field_name)

    return missing_fields
