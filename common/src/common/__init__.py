from common.llm.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    MLXEmbeddingProvider,
    MockEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    cosine_distance,
    cosine_similarity,
    create_embedding_provider,
)
from common.llm.manager import LLMManager
from common.llm.providers import (
    LLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    create_provider,
)
from common.memory import (
    EpisodicStore,
    PendingMemory,
    SessionSummary,
    Turn,
    VectorMatch,
    format_relevant_context,
    is_synthetic_context,
    should_index_turn,
)
from common.memory.store import get_episodic_store
from common.profile import ProfileEntry, ProfileStore
from common.profile.store import get_profile_store

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "create_provider",
    "LLMManager",
    "EmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "MLXEmbeddingProvider",
    "MockEmbeddingProvider",
    "EmbeddingError",
    "create_embedding_provider",
    "cosine_similarity",
    "cosine_distance",
    "ProfileStore",
    "ProfileEntry",
    "get_profile_store",
    "EpisodicStore",
    "Turn",
    "PendingMemory",
    "VectorMatch",
    "SessionSummary",
    "get_episodic_store",
    "should_index_turn",
    "is_synthetic_context",
    "format_relevant_context",
]


def main() -> None:
    """Print a greeting from the common package."""
    print("Hello from common!")
