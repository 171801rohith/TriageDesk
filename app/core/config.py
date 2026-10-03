from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Provider selection — a typo (e.g. "openai") fails validation at startup.
    llm_provider: Literal["gemini", "ollama"] = "ollama"

    # Gemini. The key is a field because pydantic-settings reads `.env` into this
    # object but does NOT export it to os.environ, where the SDK would look for it.
    # SecretStr prints as '**********', so it can't leak into logs/reprs (NFR-6).
    google_api_key: SecretStr | None = None
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"

    # Embeddings / LLM behaviour
    embedding_dim: int = 768
    llm_timeout_seconds: int = 60

    # Retrieval + guardrails
    retrieval_k: int = 4
    retrieval_max_distance: float = 0.5
    confidence_threshold: float = 0.7


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance (cached so `.env` is read once)."""
    return Settings()
