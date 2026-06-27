from app.models import (
    CitizenProfile,
    EducationLevel,
    Gender,
    InstitutionType,
    SocialCategory,
)
from app.scheme_search import search_schemes_for_profile


def main() -> None:
    # profile = CitizenProfile(
    #     age=21,
    #     state="Maharashtra",
    #     district=None,
    #     gender=Gender.female,
    #     is_student=True,
    #     education_level=EducationLevel.undergraduate,
    #     course_name="B.Tech",
    #     institution_type=InstitutionType.private,
    #     annual_family_income=180000,
    #     social_category=SocialCategory.prefer_not_to_say,
    #     has_disability=None,
    #     minority_status=None,
    #     wants_category_based_schemes=False,
    # )

    profile = CitizenProfile(
    age=21,
    state="Maharashtra",
    is_student=True,
)

    results = search_schemes_for_profile(profile)

    print(f"Found {len(results)} search result(s).")

    for result in results:
        print("\nCandidate scheme:")
        print(f"Name: {result.scheme.name}")
        print(f"Search score: {result.score}")
        print(f"Application status: {result.scheme.application_window.status.value if result.scheme.application_window else 'unknown'}")

        print("\nWhy it matched:")
        for reason in result.matched_reasons:
            print(f"- {reason}")

        if result.possible_concerns:
            print("\nPossible concerns:")
            for concern in result.possible_concerns:
                print(f"- {concern}")


if __name__ == "__main__":
    main()