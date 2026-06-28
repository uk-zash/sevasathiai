from __future__ import annotations 
from datetime import date
from enum import Enum
from typing import Any, Optional, List

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


class EducationLevel(str, Enum):
    school = "school"
    undergraduate = "undergraduate"
    postgraduate = "postgraduate"
    diploma = "diploma"
    vocational = "vocational"
    not_applicable = "not_applicable"

class InstitutionType(str, Enum):
    government = "government"
    private = "private"
    aided = "aided"
    open_university = "open_university"
    unknown = "unknown"


class SocialCategory(str, Enum):
    general = "general"
    sc = "sc"
    st = "st"
    obc = "obc"
    ews = "ews"
    prefer_not_to_say = "prefer_not_to_say"
    unknown = "unknown"

class SourceType(str, Enum):
    official_portal = "official_portal"
    official_pdf = "official_pdf"
    government_api = "government_api"
    official_notification = "official_notification"
    verified_manual_entry = "verified_manual_entry"


class GovernmentLevel(str, Enum):
    central = "central"
    state = "state"
    district = "district"
    local = "local"
    other = "other"


class SchemeCategory(str, Enum):
    education = "education"
    scholarship = "scholarship"
    skill_development = "skill_development"
    financial_assistance = "financial_assistance"
    document_support = "document_support"
    other = "other"


class MatchStatus(str, Enum):
    likely_match = "likely_match"
    possible_match = "possible_match"
    not_enough_information = "not_enough_information"
    not_a_match = "not_a_match"

class RuleOperator(str, Enum):
    equals = "equals"
    in_list = "in_list"
    max_value = "max_value"
    min_value = "min_value"
    contains_any = "contains_any"
    is_true = "is_true"
    is_false = "is_false"


class RuleFailureType(str, Enum):
    blocking = "blocking"
    missing = "missing"


class EligibilityRule(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    field_name: str = Field(
        min_length=2,
        description="CitizenProfile field that this rule checks.",
    )

    operator: RuleOperator = Field(
        description="Comparison operator used for this rule.",
    )

    expected_value: Any | None = Field(
        default=None,
        description="Single expected value for equals, is_true, or is_false checks.",
    )

    expected_values: list[Any] = Field(
        default_factory=list,
        description="List of allowed values or search terms for in_list and contains_any checks.",
    )

    min_value: float | None = Field(
        default=None,
        description="Minimum allowed numeric value for min_value checks.",
    )

    max_value: float | None = Field(
        default=None,
        description="Maximum allowed numeric value for max_value checks.",
    )

    matched_reason: str = Field(
        min_length=5,
        description="Reason shown when this rule passes.",
    )

    missing_message: str = Field(
        min_length=5,
        description="Message shown when the required profile value is missing.",
    )

    failed_reason: str = Field(
        min_length=5,
        description="Reason shown when this rule fails.",
    )

    failure_type: RuleFailureType = Field(
        default=RuleFailureType.blocking,
        description="Whether a failed rule is a blocking issue or a missing/readiness issue.",
    )

class ApplicationStatus(str, Enum):
    open = "open"
    not_yet_opened = "not_yet_opened"
    closed = "closed"
    unknown = "unknown"

class AdmissionType(str , Enum):
    first_year_regular = "first_year_regular"
    second_year_lateral_entry = "second_year_lateral_entry"
    continuing_student = "continuing_student"
    not_applicable = "not_applicable"
    unknown = "unknown"


class ApplicationWindow(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    academic_year: str | None = Field(
        default=None,
        description="Academic year for which the application window applies.",
    )

    status: ApplicationStatus = Field(
        default=ApplicationStatus.unknown,
        description="Current application status from an official source.",
    )

    opens_at: date | None = Field(
        default=None,
        description="Date when applications open, if known.",
    )

    student_deadline: date | None = Field(
        default=None,
        description="Last date for student application, if known.",
    )

    institute_verification_deadline: date | None = Field(
        default=None,
        description="Last date for institute verification, if known.",
    )

    final_verification_deadline: date | None = Field(
        default=None,
        description="Last date for final nodal verification, if known.",
    )

    notes: str | None = Field(
        default=None,
        description="Important notes about the application window.",
    )



class EvidenceSource(BaseModel):
    model_config = ConfigDict(str_strip_whitespace = True , extra="forbid")

    source_type: SourceType = Field(
        description = "Type of evidence source, e.g., official portal, government API, etc.")
    
    title: str = Field(
        min_length=3,
        description="Title of the evidence source, e.g., name of the portal or document title.")
    
    publisher: str = Field(
        min_length=2,
        description="Organization or department that published the source.",
    )

    url: HttpUrl = Field(
        description="Official URL where the information was found.",
    )

    last_checked_at: date = Field(
        description="Date when this source was last checked by our system or maintainer.",
    )

    notes: str | None = Field(
        default=None,
        description="Optional notes about the source.",
    )


class Scheme(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra = "forbid")

    scheme_id: str = Field(
        min_length=3,
        pattern=r"^[a-z0-9_\-]+$",
        description="Stable unique ID for the scheme inside our database.",
    )

    name: str = Field(
        min_length=3,
        description="Official or commonly used scheme name.",
    )

    category: SchemeCategory = Field(
        description="Category of the scheme.",
    )

    government_level: GovernmentLevel = Field(
        description="Whether this is a central, state, district, local, or other scheme.",
    )

    state: str | None = Field(
        default=None,
        description="State where the scheme applies. Use None for all-India schemes.",
    )

    summary: str = Field(
        min_length=20,
        description="Short plain-language summary of what the scheme provides.",
    )

    target_groups: list[str] = Field(
        default_factory=list,
        description="Groups the scheme is meant for, such as students, girls, SC/ST students, or disabled students.",
    )

    benefits: list[str] = Field(
        default_factory=list,
        description="Benefits provided by the scheme.",
    )

    required_documents: list[str] = Field(
        default_factory=list,
        description="Documents usually required for application.",
    )

    eligibility_text: list[str] = Field(
        default_factory=list,
        description="Human-readable eligibility rules collected from official sources.",
    )

    eligibility_rules: list[EligibilityRule] = Field(
        default_factory=list,
        description="Machine-readable eligibility and readiness rules for the generic rule engine.",
    )

    application_steps: list[str] = Field(
    default_factory=list,
    description="Basic steps to apply or verify application process.",
    )

    application_window: ApplicationWindow | None = Field(
    default=None,
    description="Current or most recently verified application window.",
    )


    official_apply_url: HttpUrl | None = Field(
        default=None,
        description="Official apply URL if available.",
    )

    sources: list[EvidenceSource] = Field(
        min_length=1,
        description="At least one evidence source is required for every scheme.",
    )

    @field_validator("state")
    @classmethod
    def empty_state_to_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value
    

class SchemeSearchResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    scheme: Scheme = Field(
        description="The scheme that matched the user's profile during search.",
    )

    score: float = Field(
        ge=0,
        le=1,
        description="Search relevance score between 0 and 1. This is not eligibility confidence.",
    )

    matched_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why this scheme looked relevant during search.",
    )

    possible_concerns: list[str] = Field(
        default_factory=list,
        description="Concerns or missing details noticed during search.",
    )


class RecommendationLabel(str, Enum):
    strong_match = "strong_match"
    possible_match = "possible_match"
    needs_information = "needs_information"
    not_recommended = "not_recommended"


class RankedSchemeResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search_result: SchemeSearchResult = Field(
        description="Original search result for this scheme.",
    )

    eligibility_result: EligibilityResult = Field(
        description="Eligibility or readiness result for this scheme.",
    )

    rank_score: float = Field(
        ge=0,
        le=1,
        description="Combined ranking score based on search relevance and eligibility result.",
    )

    recommendation_label: RecommendationLabel = Field(
        description="Human-friendly recommendation category.",
    )

    rank_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons explaining why this scheme received this ranking.",
    )


class EligibilityResult(BaseModel):
    scheme_id: str = Field(
        min_length=3,
        description="ID of the scheme that was checked.",
    )

    status: MatchStatus = Field(
        description="Eligibility matching status based on available user information.",
    )

    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence score between 0 and 1. This is not a guarantee of eligibility.",
    )

    matched_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why the user appears to match the scheme.",
    )

    missing_information: list[str] = Field(
        default_factory=list,
        description="Information still needed to make a better eligibility assessment.",
    )

    not_matched_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why the user does not appear to match the scheme.",
    )

    user_message: str = Field(
        min_length=20,
        description="Plain-language message that can be shown to the user.",
    )

    @model_validator(mode="after")
    def validate_reasoning(self) -> "EligibilityResult":
        if self.status in {MatchStatus.likely_match, MatchStatus.possible_match}:
            if not self.matched_reasons:
                raise ValueError("Likely or possible matches must include at least one matched reason.")

        if self.status == MatchStatus.not_enough_information:
            if not self.missing_information:
                raise ValueError("Not-enough-information results must explain what information is missing.")

        if self.status == MatchStatus.not_a_match:
            if not self.not_matched_reasons:
                raise ValueError("Not-a-match results must include at least one reason.")

        return self


class CitizenProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    age: int | None = Field(default=None, ge=0, le=120, description="User's age in years.")
    state: str | None = Field(default=None, description="Indian state or union territory where the user lives")
    district: str | None = Field(
        default=None,
        description="District where the user lives. Optional because many schemes only need state.",
    )

    gender: Gender | None = Field(
        default=None,
        description="Gender, if the user wants to share it.",
    )

    is_student: bool | None = Field(
        default=None,
        description="Whether the user is currently a student.",
    )

    education_level: EducationLevel | None = Field(
        default=None,
        description="Current education level of the user.",
    )

    course_name: str | None = Field(
        default=None,
        description="Course or class name, for example B.Tech, BA, Class 12, ITI.",
    )

    institution_type: InstitutionType | None = Field(
        default=None,
        description="Type of institution where the user studies.",
    )

    admission_type: AdmissionType | None = Field(
        default = None,
        description = "How the user was admitted to the course, such as first year regular or second year lateral entry.",
    )

    is_aicte_approved_institution: bool | None = Field(
        default=None,
        description="Whether the user's institution is AICTE-approved, if known."
    )

    annual_family_income: float | None = Field(
        default=None,
        ge=0,
        description="Approximate annual family income in INR.",
    )

    has_valid_income_certificate: bool | None = Field(
        default=None,
        description="Whether the user has a valid income certificate issued by the State/UT Government.",
    )

    girl_children_in_family: int | None = Field(
        default=None,
        ge=0,
        le=20,
        description="Number of girl children in the family, if relevant and the user wants to share.",
    )

    receiving_other_scholarship: bool | None = Field(
        default=None,
        description="Whether the user is already receiving another scholarship or financial assistance.",
    )

    social_category: SocialCategory | None = Field(
        default=None,
        description="Social category. Optional and privacy-sensitive.",
    )

    has_disability: bool | None = Field(
        default=None,
        description="Whether the user has a disability, if they want to share it.",
    )

    disability_percentage: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Disability percentage, if the user wants to share it and it is relevant to a scheme.",
    )

    minority_status: bool | None = Field(
        default=None,
        description="Whether the user belongs to a minority community, if they want to share it.",
    )

    wants_category_based_schemes: bool | None = Field(
        default=False,
        description="Whether the user wants us to consider category-based schemes.",
    )

    @field_validator("state", "district", "course_name")
    @classmethod
    def empty_string_to_none(cls, value:str | None) -> str | None:
        if value == "":
            return None
        return value


class ProfileExtractionResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    profile: CitizenProfile = Field(
        description="Structured citizen profile extracted from the user's message.",
    )

    confidence: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Confidence in the extraction quality. This is not eligibility confidence.",
    )

    missing_fields: list[str] = Field(
        default_factory=list,
        description="Important profile fields that were not found in the user's message.",
    )

    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made during extraction. Prefer leaving this empty instead of guessing.",
    )

    privacy_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings if the user shared or requested use of sensitive information.",
    )


## TAOR Trace Models

class AgentAction(str, Enum):
    extract_profile = "extract_profile"
    search_schemes = "search_schemes"
    check_eligibility = "check_eligibility"
    rank_results = "rank_results"
    ask_follow_up = "ask_follow_up"
    final_response = "final_response"


class AgentStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    step_number: int = Field(
        ge=1,
        description="Step number in the TAOR loop.",
    )

    thought: str = Field(
        min_length=5,
        description="High-level reason for the next action.",
    )

    action: AgentAction = Field(
        description="Action selected by the agent.",
    )

    observation: str = Field(
        min_length=5,
        description="What the agent observed after taking the action.",
    )

    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured data captured for debugging or trace display.",
    )

class AgentRunResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    profile: CitizenProfile | None = Field(
        default=None,
        description="Extracted citizen profile, if extraction succeeded.",
    )

    search_results: list[SchemeSearchResult] = Field(
        default_factory=list,
        description="Candidate scheme search results.",
    )

    eligibility_results: list[EligibilityResult] = Field(
        default_factory=list,
        description="Eligibility or readiness results for candidate schemes.",
    )

    ranked_results: list[RankedSchemeResult] = Field(
        default_factory=list,
        description="Ranked scheme results combining search relevance and eligibility/readiness checks.",
    )

    steps: list[AgentStep] = Field(
        default_factory=list,
        description="TAOR trace steps.",
    )

    needs_follow_up: bool = Field(
        default=False,
        description="Whether the agent needs more information from the user.",
    )

    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="Questions the agent should ask the user next.",
    )

    final_message: str = Field(
        min_length=5,
        description="Final user-facing message for this run.",
    )
