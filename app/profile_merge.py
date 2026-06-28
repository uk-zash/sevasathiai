from typing import Optional
from app.models import CitizenProfile, SocialCategory

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
    if existing_profile is None:
        return update

    merged_data = existing_profile.model_dump()
    update_data = update.model_dump()

    for field_name, value in update_data.items():
        if field_name == "wants_category_based_schemes":
            continue

        if value is not None:
            merged_data[field_name] = value

    if update.wants_category_based_schemes is True:
        merged_data["wants_category_based_schemes"] = True

    if update.social_category == SocialCategory.prefer_not_to_say:
        merged_data["wants_category_based_schemes"] = False

    return CitizenProfile.model_validate(merged_data)

def get_basic_missing_profile_fields(profile: CitizenProfile) -> list[str]:
    missing_fields: list[str] = []

    for field_name in IMPORTANT_BASIC_FIELDS:
        value = getattr(profile, field_name)

        if value is None:
            missing_fields.append(field_name)

        # Note: If you encounter an error here on Python 3.9 with `list[str]`,
        # you can also import `List` from typing and change it to `List[str]`.
        # However, Python 3.9 generally supports list[str] inside function bodies 
        # better than the `|` operator, so this should run fine!

    return missing_fields