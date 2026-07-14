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

    # AI backend: "mock" (offline, agent-aware heuristic), "ollama", or
    # "anythingllm" (RAG assistant). All fall back to mock on error.
    ai_backend: str = "mock"

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    anythingllm_url: str = "http://localhost:3001"
    anythingllm_api_key: str = ""
    anythingllm_workspace: str = "acmeco"

    # Optional OpenSearch cluster powering document search (status only for now).
    opensearch_url: str = ""
    opensearch_cluster: str = "acmeco-os"

    app_name: str = "AcmeCO"
    app_tagline: str = "OpenSearch • AnythingLLM"


settings = Settings()
