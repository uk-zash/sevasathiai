"""Environment-backed application settings."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    groq_api_key: SecretStr = Field(
        validation_alias="GROQ_API_KEY",
        description="Groq API key used to call the LLM.",
    )

    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias="GROQ_MODEL",
        description="Groq model used for LLM calls.",
    )

    app_env: str = Field(
        default="development",
        validation_alias="APP_ENV",
        description="Application environment name.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Importing `settings` gives the rest of the app one validated config object.
settings = Settings()
