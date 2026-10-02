"""LLM provider factory — the ONLY module that knows about Gemini vs Ollama.

Everything else receives LangChain's common interfaces (`BaseChatModel`,
`Embeddings`), so switching `LLM_PROVIDER` touches no other code (FR-19).
This module must not import from any feature package (kb, tickets, triage).
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.core.config import get_settings

LLM_MAX_RETRIES = 2  # NFR-4


def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """Build the chat model for the configured provider.

    Args:
        temperature: 0.0 for classification, ~0.2 for drafting (requirements §7).

    TODO (implement_1.md Phase 3):
        - gemini → `ChatGoogleGenerativeAI(model=..., temperature=..., timeout=...,
          max_retries=LLM_MAX_RETRIES)`; reads GOOGLE_API_KEY from env.
        - ollama → `ChatOllama(model=..., base_url=..., temperature=...)`;
          decide how to enforce `llm_timeout_seconds` (see `client_kwargs`).
        - Import each provider package inside its branch so the unused one isn't loaded.
    """
    raise NotImplementedError("get_chat_model")


def get_embeddings() -> Embeddings:
    """Build the embeddings model for the configured provider (768-d for both).

    TODO (implement_1.md Phase 3):
        - gemini → `GoogleGenerativeAIEmbeddings(model=..., output_dimensionality=embedding_dim)`
        - ollama → `OllamaEmbeddings(model=..., base_url=...)`
    """
    raise NotImplementedError("get_embeddings")


def active_model_info() -> dict[str, str]:
    """Describe the active provider for `/health` and `triage_runs` rows.

    Reads config only — builds no clients, so it works even when the provider is down.
    The keys must match `HealthOut` fields and `TriageRun` columns (callers unpack it).

    Returns:
        ``{"provider": ..., "chat_model": ..., "embedding_model": ...}``
    """
    settings = get_settings()

    provider = settings.llm_provider
    is_gemini = provider == "gemini"

    return {
        "provider": provider,
        "chat_model": (
            settings.gemini_chat_model
            if is_gemini
            else settings.ollama_chat_model
        ),
        "embedding_model": (
            settings.gemini_embed_model
            if is_gemini
            else settings.ollama_embed_model
        ),
    }
