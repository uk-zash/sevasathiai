from groq import Groq

from app.settings import settings

def get_groq_client() -> Groq:
    """
    Returns a Groq client instance configured with the API key and model from settings.
    """
    return Groq(api_key=settings.groq_api_key.get_secret_value())

def ask_groq_once(user_message: str) -> str:
    """
    Sends a single user message to the Groq LLM and returns the response.
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

    if content is None:
        return "No response content was returned by the model."

    return content