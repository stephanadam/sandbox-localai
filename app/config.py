from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-insecure-secret-change-me"
    database_url: str = "sqlite:///./legal_analyst.db"

    # AI backend: "mock" (built-in heuristic) or "ollama" (local LLM server).
    ai_backend: str = "mock"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    app_name: str = "Legal Analyst"


settings = Settings()
