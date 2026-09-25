"""Typed application settings loaded from the environment / `.env`.

One place for every knob (provider, model names, thresholds). Switching LLM
provider is a config change here, never a code change (FR-19, F8).
See architecture.md §7 for the full variable list.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Provider selection — a typo (e.g. "openai") fails validation at startup.
    llm_provider: Literal["gemini", "ollama"] = "ollama"

    # Gemini (GOOGLE_API_KEY is read directly from the env by langchain-google-genai;
    # it is intentionally NOT a field here so it can never be logged — NFR-6).
    gemini_chat_model: str = "gemini-3.7-flash"
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
