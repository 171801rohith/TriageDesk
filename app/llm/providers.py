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

    Every call is bounded by `llm_timeout_seconds` (NFR-4); a timeout raises, and the
    workflow turns that into `needs_review` (FR-13).

    Raises:
        pydantic.ValidationError: provider is gemini and no GOOGLE_API_KEY is set.
    """
    settings = get_settings()

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Pass temperature/retries explicitly: the class defaults are 0.7 and 6.
        return ChatGoogleGenerativeAI(
            model=settings.gemini_chat_model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            timeout=settings.llm_timeout_seconds,
            max_retries=LLM_MAX_RETRIES,
        )

    from langchain_ollama import ChatOllama

    # ChatOllama has no timeout/max_retries fields; `client_kwargs` goes to the
    # underlying httpx client. No retries: Ollama is local, so a retry after a
    # timeout would only multiply the wait before the ticket falls back to review.
    return ChatOllama(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
        temperature=temperature,
        client_kwargs={"timeout": settings.llm_timeout_seconds},
    )


def get_embeddings() -> Embeddings:
    """Build the embeddings model for the configured provider (768-d for both).

    Both must match `kb_chunks.embedding` = vector(768). Provider packages are
    imported inside their branch so the unused one is never loaded.

    Raises:
        pydantic.ValidationError: provider is gemini and no GOOGLE_API_KEY is set.
    """
    settings = get_settings()

    if settings.llm_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        # gemini-embedding-001 defaults to 3072 dims; truncate to the column size.
        return GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embed_model,
            google_api_key=settings.google_api_key,
            output_dimensionality=settings.embedding_dim,
        )

    from langchain_ollama import OllamaEmbeddings

    # nomic-embed-text is natively 768-d, so no dimension argument is needed.
    return OllamaEmbeddings(model=settings.ollama_embed_model, base_url=settings.ollama_base_url)


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
