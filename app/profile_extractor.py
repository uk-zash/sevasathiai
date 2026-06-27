from pydantic import ValidationError

from app.llm_client import get_groq_client
from app.models import ProfileExtractionResult
from app.settings import settings



PROFILE_EXTRACTION_SYSTEM_PROMPT = """
You are SevaSathi AI's profile extraction component.

Your task is to extract only the citizen profile details that are clearly present
in the user's message.

Rules:
1. Do not guess missing details.
2. Use null for unknown profile fields.
3. Convert income written in lakhs into INR numbers.
   Example: "1.8 lakh" means 180000.
4. Do not store Aadhaar numbers, bank account numbers, OTPs, certificate IDs,
   phone numbers, or other sensitive identifiers.
5. If the user shares sensitive information, add a privacy warning.
6. Do not recommend schemes in this step.
7. Do not decide eligibility in this step.
8. Return only data that matches the provided JSON schema.
"""


def extract_profile_from_text(user_text:str) -> ProfileExtractionResult:
    client = get_groq_client()

    response = client.chat.completions.create(
        model = settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": PROFILE_EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],

        response_format = {
            "type": 'json_schema',
            "json_schema": {
                "name": "profile_extraction_result",
                "strict": False,
                "schema": ProfileExtractionResult.model_json_schema(),
            },
        },
        temperature=0,
        max_completion_tokens=900
    )
    content = response.choices[0].message.content

    if content is None:
        raise ValueError("Groq returned an empty response")
    
    try:
        return ProfileExtractionResult.model_validate_json(content)
    
    except ValidationError as error:
        raise ValueError(
            "Groq returned JSON, but it did not match our ProfileExtractionResult model."
        ) from error