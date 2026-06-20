"""LLM integration: LiteLLM gateway, OpenRouter adapter, embeddings, and retrieval."""

from dharmiq.llm.embeddings import EmbeddingBackend, get_embedding_backend
from dharmiq.llm.litellm_service import LiteLLMService, get_litellm_service
from dharmiq.llm.openrouter_client import OpenRouterClient, get_openrouter_client
from dharmiq.llm.retrieval import RetrievedChunk, retrieve_document_chunks

__all__ = [
    "EmbeddingBackend",
    "LiteLLMService",
    "OpenRouterClient",
    "RetrievedChunk",
    "get_embedding_backend",
    "get_litellm_service",
    "get_openrouter_client",
    "retrieve_document_chunks",
]
