from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-insecure-secret-change-me"
    database_url: str = "sqlite:///./legal_analyst.db"

    # Where uploaded documents are stored on the local server.
    upload_dir: str = "./uploads"

    # Directory for the rotating audit log of transactions & AI responses.
    log_dir: str = "./logs"

    # ----- LLM connectivity -----
    # Default target when a request doesn't specify one. One of:
    #   "local" -> a local Ollama server (private, on your machine)
    #   "cloud" -> an OpenAI-compatible Cloud API
    #   "mock"  -> offline heuristic (no service needed; safe default)
    llm_target: str = "mock"

    # Local (Ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Cloud API (OpenAI-compatible: OpenAI, Together, Groq, vLLM, etc.)
    cloud_api_key: str = ""
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_model: str = "gpt-4o-mini"

    # ----- SEC EDGAR -----
    # SEC requires a contact string in the User-Agent. Set to your name + email.
    edgar_identity: str = "AcmeCO Research research@example.com"

    app_name: str = "AcmeCO"
    app_tagline: str = "SEC EDGAR • Local + Cloud AI"


settings = Settings()
