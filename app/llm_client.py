"""Small Groq client wrapper used by LLM-powered parts of the app."""

from groq import Groq

from app.settings import settings

def get_groq_client() -> Groq:
    """Return a Groq client configured with the validated API key."""
    return Groq(api_key=settings.groq_api_key.get_secret_value())

def ask_groq_once(user_message: str) -> str:
    """Send one simple prompt to Groq and return plain response text.

    This helper is separate from structured profile extraction. It is useful for
    quick experiments or future simple assistant responses where no JSON schema
    is required.
    """
    client = get_groq_client()
    chat_completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are SevaSathi AI, a careful public-service assistant. "
                    "Do not claim final eligibility for welfare schemes. "
                    "Explain that official verification is required."
                ),
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
        temperature=0.2,
        max_completion_tokens=300,
    )

    content = chat_completion.choices[0].message.content

    # Defensive fallback: keep callers from handling None responses themselves.
    if content is None:
        return "No response content was returned by the model."

    return content
