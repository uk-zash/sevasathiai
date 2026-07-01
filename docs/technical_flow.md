# SevaSathi AI Technical Flow

This document explains how SevaSathi AI currently works behind the scenes: how a user asks a question, how the system extracts a profile, how schemes are searched and ranked, how follow-up questions are generated, and how answers are merged back into the next run.

The important design principle is:

> The app should work for any scheme added to `data/schemes.json` as long as that scheme has machine-readable `eligibility_rules` using fields already present in `CitizenProfile`.

---

## 1. Main Runtime Pieces

| Layer | File | Responsibility |
| --- | --- | --- |
| UI | `streamlit_app.py` | Shows forms, stores session state, renders results, handles follow-up answers. |
| Agent orchestration | `app/taor_agent.py` | Runs extract -> search -> eligibility -> rank -> follow-up/final response. |
| Profile extraction | `app/profile_extractor.py` | Uses the LLM to convert user text into `CitizenProfile`. |
| Profile merge | `app/profile_merge.py` | Merges follow-up profile updates into previous profile. |
| Scheme loading | `app/scheme_loader.py` | Loads and validates `data/schemes.json`. |
| Search | `app/scheme_search.py` | Scores candidate schemes using rule matches, state, and text overlap. |
| Eligibility | `app/rule_engine.py`, `app/eligibility_checker.py` | Applies scheme `eligibility_rules` to the profile. |
| Ranking | `app/ranking.py` | Combines search score and eligibility status. |
| Follow-up parsing | `app/follow_up_parser.py` | Deterministically converts UI follow-up answers into profile updates. |
| Output | `app/output_writer.py` | Builds markdown report and JSON trace. |

---

## 2. High-Level Flow

```text
User enters details
        |
        v
Streamlit calls SevaSathiTAORAgent.run(...)
        |
        v
LLM extracts CitizenProfile from user text
        |
        v
Profile is merged with previous profile, if this is a follow-up
        |
        v
Schemes are loaded from data/schemes.json
        |
        v
Search scores schemes using eligibility_rules + query text + state
        |
        v
Top candidates are checked with rule engine
        |
        v
Candidates are ranked
        |
        +---------------------+
        |                     |
        v                     v
Missing info?            Enough info?
Ask follow-up            Show final ranked guidance
        |
        v
User answers follow-up
        |
        v
Answers update profile
        |
        v
Agent runs again with original search intent
```

---

## 3. Initial User Question Flow

Example user input:

```text
I am a 21-year-old female B Tech student from Maharashtra.
My family income is 2 lakh. I need scholarship help.
```

In `streamlit_app.py`, initial submission calls:

```python
run_agent_and_store_result(
    user_text=user_text,
    existing_profile=None,
)
```

When `existing_profile` is `None`, Streamlit stores the original user query:

```python
st.session_state.search_query_text = user_text
```

This is important because follow-up answers like “Yes” or “B Tech” should not replace the original intent. On later follow-up runs, the app still searches using the original query text.

---

## 4. Profile Extraction

`app/profile_extractor.py` sends the user text to the LLM and asks for a strict JSON object matching `ProfileExtractionResult`.

The result contains:

```python
ProfileExtractionResult(
    profile=CitizenProfile(...),
    confidence=...,
    missing_fields=[...],
    assumptions=[...],
    privacy_warnings=[...],
)
```

The extracted profile is intentionally cautious:

- It does not guess missing fields.
- It converts income like `2 lakh` into `200000`.
- It avoids storing sensitive identifiers.
- It uses `null` for unknown profile fields.

Example extracted profile:

```json
{
  "age": 21,
  "state": "Maharashtra",
  "gender": "female",
  "is_student": true,
  "education_level": "undergraduate",
  "course_name": "B Tech",
  "annual_family_income": 200000
}
```

---

## 5. Profile Merge

On follow-up, the app already has an existing profile. The new extracted or deterministic profile update is merged with the previous profile in `app/profile_merge.py`.

Example:

```python
existing_profile = CitizenProfile(
    is_student=True,
    course_name="B Tech",
)

update = CitizenProfile(
    has_disability=True,
    disability_percentage=45,
)

merged = merge_citizen_profiles(existing_profile, update)
```

Result:

```json
{
  "is_student": true,
  "course_name": "B Tech",
  "has_disability": true,
  "disability_percentage": 45
}
```

The merge rule is simple: non-null new values replace missing/old values, while missing values do not erase previous answers.

---

## 6. Scheme Data Model

Schemes live in:

```text
data/schemes.json
```

Each scheme is validated by the `Scheme` model in `app/models.py`.

The most important fields for matching are:

```json
{
  "scheme_id": "example_scheme",
  "name": "Example Scheme",
  "summary": "Plain language summary.",
  "target_groups": ["students", "minority applicants"],
  "eligibility_text": ["Human-readable eligibility rules."],
  "eligibility_rules": []
}
```

For generic behavior, `eligibility_rules` are the key.

---

## 7. Eligibility Rules

Each `EligibilityRule` tells the system:

- which profile field to check,
- how to check it,
- what message to show if it matches,
- what message to show if it is missing,
- what message to show if it fails,
- whether failure is blocking or only missing/readiness-related.

Example rule:

```json
{
  "field_name": "annual_family_income",
  "operator": "max_value",
  "expected_value": null,
  "expected_values": [],
  "min_value": null,
  "max_value": 300000,
  "matched_reason": "The applicant is within the income limit.",
  "missing_message": "Applicant income detail is required.",
  "failed_reason": "Applicant is above the income limit.",
  "failure_type": "blocking"
}
```

Supported operators:

| Operator | Meaning |
| --- | --- |
| `equals` | Profile value must equal `expected_value`. |
| `in_list` | Profile value must be one of `expected_values`. |
| `max_value` | Numeric profile value must be <= `max_value`. |
| `min_value` | Numeric profile value must be >= `min_value`. |
| `contains_any` | Text profile value must contain at least one expected term. Punctuation/spacing is normalized, so `B Tech`, `B.Tech`, and `BTech` can match. |
| `is_true` | Profile value must be `true`. |
| `is_false` | Profile value must be `false`. |

Failure types:

| `failure_type` | Behavior |
| --- | --- |
| `blocking` | If the user clearly fails this rule, the scheme is not recommended. |
| `missing` | If the user fails this readiness check, the system treats it as missing/uncertain information instead of a hard no. |

---

## 8. Search Flow

Search happens in `app/scheme_search.py`.

```python
search_results = search_schemes_for_profile(
    profile,
    query_text=search_query_text,
)
```

The current search score comes from:

1. State match:
   - all-India schemes get a small score,
   - matching state gets a higher score,
   - different state blocks the scheme.

2. Rule-driven profile scoring:
   - if a scheme has `eligibility_rules`, each matched rule contributes to search relevance,
   - a clear blocking rule failure returns score `0`,
   - missing details become concerns and can later produce follow-up questions.

3. Query text overlap:
   - the original user query is tokenized,
   - scheme text is tokenized,
   - overlapping meaningful terms add relevance.

4. Application window:
   - open application window adds a small score.

Default behavior filters out results below `min_score=0.25`.

---

## 9. Eligibility Checking

Eligibility checking happens after search. In `app/eligibility_checker.py`:

```python
eligibility = check_eligibility_for_scheme(
    profile=profile,
    scheme=scheme,
)
```

For any scheme with `eligibility_rules`, the generic rule engine is used:

```python
check_scheme_with_rules(profile, scheme)
```

The result is:

```python
EligibilityResult(
    scheme_id="...",
    status=MatchStatus.possible_match,
    confidence=0.6,
    matched_reasons=[...],
    missing_information=[...],
    not_matched_reasons=[...],
    user_message="..."
)
```

Status meanings:

| Status | Meaning |
| --- | --- |
| `likely_match` | No missing info and no blocking issues. |
| `possible_match` | Enough checks matched, but some details are missing/uncertain. |
| `not_enough_information` | Too little information to assess confidently. |
| `not_a_match` | At least one blocking rule clearly failed. |

---

## 10. Ranking

Ranking happens in `app/ranking.py`.

```python
ranked_results = rank_scheme_results(
    search_results=search_results,
    eligibility_results=eligibility_results,
)
```

Ranking combines:

- eligibility status,
- search score,
- missing-information penalty,
- blocking-issue penalty.

Schemes with `not_a_match` are treated as non-actionable before final UI display. If all checked candidates are blocked, the app shows a clean no-match response.

---

## 11. Follow-Up Question Generation

Follow-up generation happens in `SevaSathiTAORAgent._build_follow_up_questions`.

The system:

1. Looks at all actionable ranked schemes, not just the top one.
2. Reads each scheme’s `missing_information`.
3. Matches the missing message back to the `EligibilityRule` that produced it.
4. Uses the rule’s `field_name` to choose a question.
5. Returns up to 3 unique questions.

This is why a girl-student match can still ask about disability: another actionable scheme may also apply if the disability detail is provided.

Example:

```python
FIELD_QUESTION_MAP = {
    "has_disability": (
        "Does the specially-abled or disability condition apply to you for this scheme? "
        "You may answer Yes, No, or Prefer not to say."
    ),
    "disability_percentage": (
        "What is your disability percentage as mentioned on your disability certificate? "
        "You may skip this if you are not comfortable sharing."
    ),
}
```

If a new scheme uses a field already in `CitizenProfile`, follow-up questions can be generated automatically.

If the field is not in the map, the fallback is generic:

```text
What is your annual family income?
Can you confirm whether minority status applies?
Please provide your course name.
```

Application-window uncertainty is not asked as a user follow-up because the user cannot answer official portal status reliably.

---

## 12. Follow-Up UI Behavior

When follow-up questions exist, the UI intentionally does not show scheme analysis.

In `streamlit_app.py`:

```python
if result.needs_follow_up:
    st.subheader("More information needed")
    st.warning("More details are needed before stronger guidance can be given.")
    st.markdown(result.final_message)
    render_follow_up_form()
    return
```

The user sees:

```text
I need a little more information before I can show the best verified matches.
Please answer the questions below. You may skip any question you are not comfortable answering.
```

Then only the follow-up form is shown.

---

## 13. Follow-Up Answer Flow

When the user answers follow-up questions, Streamlit creates:

```python
answered_pairs = [
    ("What course are you studying?", "B Tech"),
    ("Does the specially-abled or disability condition apply?", "Yes, I have a disability"),
]
```

Two things happen:

### 13.1 LLM follow-up context

The app builds a text block for the LLM:

```python
follow_up_context = build_follow_up_context_from_answers(answered_pairs)
```

Example:

```text
The user is answering follow-up questions from SevaSathi AI.
Use each question as context for the answer. Extract only clearly stated profile details.

Question 1: What course are you studying?
Answer 1: B Tech

Question 2: Does the specially-abled or disability condition apply to you for this scheme?
Answer 2: Yes, I have a disability
```

### 13.2 Deterministic parser

The app also parses answers deterministically:

```python
deterministic_profile_update = profile_update_from_follow_up_answers(answered_pairs)
```

Example output:

```json
{
  "course_name": "B Tech",
  "has_disability": true
}
```

Then it merges with the current profile:

```python
merged_profile = merge_citizen_profiles(
    existing_profile=st.session_state.profile,
    update=deterministic_profile_update,
)
```

Finally, the agent runs again:

```python
run_agent_and_store_result(
    user_text=follow_up_context,
    existing_profile=merged_profile,
    search_query_text=st.session_state.search_query_text,
)
```

Notice that `search_query_text` stays the original query. This preserves the user’s original intent across follow-up rounds.

---

## 14. Final Guidance vs No Match

### Final guidance

If there are actionable ranked results and no more important follow-up questions, the app shows:

- ranked scheme names,
- recommendation label,
- eligibility status,
- ranking score,
- matched checks,
- missing/uncertain info if any,
- documents,
- application window,
- official sources.

### No match

If all checked candidates are blocked, or no candidate can be found after enough information is available, the app shows:

```text
I could not find a verified scheme match from the current local database based on the details provided.
You can try again with different or corrected details, or verify directly on official portals.
```

It does not list scheme names with `not_recommended` analysis in the user-facing no-match state.

---

## 15. Adding a New Scheme

To add a new scheme, add a new object to `data/schemes.json`.

Minimum pattern:

```json
{
  "scheme_id": "test_senior_income_support",
  "name": "Test Senior Income Support",
  "category": "financial_assistance",
  "government_level": "state",
  "state": "Maharashtra",
  "summary": "Financial assistance for senior citizens from low-income households.",
  "target_groups": ["senior citizens", "low-income households"],
  "benefits": ["Monthly income support."],
  "required_documents": ["Age proof", "Income proof"],
  "eligibility_text": [
    "Applicant should be at least 60 years old.",
    "Annual family income should be at or below Rs. 3 lakh."
  ],
  "eligibility_rules": [
    {
      "field_name": "age",
      "operator": "min_value",
      "expected_value": null,
      "expected_values": [],
      "min_value": 60,
      "max_value": null,
      "matched_reason": "The applicant meets the minimum age requirement.",
      "missing_message": "Applicant age detail is required.",
      "failed_reason": "Applicant is below the minimum age requirement.",
      "failure_type": "blocking"
    },
    {
      "field_name": "annual_family_income",
      "operator": "max_value",
      "expected_value": null,
      "expected_values": [],
      "min_value": null,
      "max_value": 300000,
      "matched_reason": "The applicant is within the income limit.",
      "missing_message": "Applicant income detail is required.",
      "failed_reason": "Applicant is above the income limit.",
      "failure_type": "blocking"
    }
  ],
  "application_steps": ["Apply through the official portal."],
  "application_window": null,
  "official_apply_url": "https://example.gov.in/apply",
  "sources": [
    {
      "source_type": "official_portal",
      "title": "Official Scheme Page",
      "publisher": "Example Department",
      "url": "https://example.gov.in/apply",
      "last_checked_at": "2026-06-27",
      "notes": null
    }
  ]
}
```

This scheme will automatically support:

- search by query text,
- state filtering,
- rule-driven matching,
- follow-up questions for `age` and `annual_family_income`,
- final ranking,
- no-match behavior when rules fail.

---

## 16. When Code Changes Are Still Needed

Adding a scheme is data-only if it uses existing `CitizenProfile` fields.

Current useful fields include:

```text
age
state
district
gender
is_student
education_level
course_name
institution_type
admission_type
is_aicte_approved_institution
annual_family_income
has_valid_income_certificate
girl_children_in_family
receiving_other_scholarship
social_category
has_disability
disability_percentage
minority_status
wants_category_based_schemes
```

Code changes are needed if a new scheme needs a profile field that does not exist yet.

Example:

```text
land_ownership_status
widow_status
occupation
bank_account_available
domicile_years
```

For a new field, update:

1. `CitizenProfile` in `app/models.py`
2. extraction prompt in `app/profile_extractor.py`
3. `FIELD_QUESTION_MAP` in `app/taor_agent.py`
4. `profile_update_from_follow_up_answers` in `app/follow_up_parser.py`
5. `render_follow_up_answer_input` in `streamlit_app.py`
6. tests

---

## 17. Example Programmatic Run

```python
from app.taor_agent import SevaSathiTAORAgent

agent = SevaSathiTAORAgent()

result = agent.run(
    user_text=(
        "I am a 21-year-old female B Tech student from Maharashtra. "
        "My family income is 2 lakh. I need scholarship help."
    )
)

print(result.needs_follow_up)
print(result.follow_up_questions)
print(result.final_message)
```

If follow-up is needed:

```python
from app.follow_up_parser import profile_update_from_follow_up_answers
from app.profile_merge import merge_citizen_profiles

answers = [
    (
        "Does the specially-abled or disability condition apply to you for this scheme?",
        "Yes, I have a disability",
    ),
    (
        "What is your disability percentage as mentioned on your disability certificate?",
        "45%",
    ),
]

update = profile_update_from_follow_up_answers(answers)
merged_profile = merge_citizen_profiles(result.profile, update)

next_result = agent.run(
    user_text="The user answered follow-up questions.",
    existing_profile=merged_profile,
    search_query_text=(
        "I am a 21-year-old female B Tech student from Maharashtra. "
        "My family income is 2 lakh. I need scholarship help."
    ),
)
```

---

## 18. Testing

Run all tests:

```bash
.venv/bin/python -m pytest
```

Important test files:

| Test file | What it proves |
| --- | --- |
| `tests/test_generic_scheme_support.py` | New rule-driven schemes work without scheme-specific code. |
| `tests/test_scheme_search.py` | Search ranking, query intent, and technical-course variants. |
| `tests/test_rule_engine.py` | Generic eligibility rule behavior. |
| `tests/test_taor_agent_follow_up.py` | Follow-up generation and no-match behavior. |
| `tests/test_follow_up_parser.py` | Follow-up answers update the profile deterministically. |

---

## 19. Current Technical Guarantees

The system currently guarantees:

- Schemes with `eligibility_rules` are evaluated generically.
- Clear blocking failures are not shown as recommendations.
- Follow-up questions are asked before showing analysis.
- Follow-up questions can cover multiple plausible schemes.
- Follow-up answers are merged into the existing profile.
- The original user intent is preserved across follow-up rounds.
- If no actionable match remains, the UI shows no-match instead of scheme-by-scheme rejection details.

The main limitation:

- Generic support depends on `CitizenProfile`. If a scheme needs a new profile field, that field must be added to the model, extractor, follow-up parser, UI, and tests.
