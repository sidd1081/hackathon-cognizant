"""Local embedding layer using Sentence Transformers.

Embeddings are generated **locally** with the model named in
``settings.embedding_model`` (default ``sentence-transformers/all-MiniLM-L6-v2``).
Groq is used only for the LLM, never for embeddings.

The model is loaded once (thread-safe) and reused. ``embed_texts`` encodes an
entire list in a single batched call — it never loops one sentence at a time —
and returns L2-normalized ``float32`` NumPy arrays (so a dot product equals
cosine similarity, which is what the FAISS stage will rely on).
"""

from __future__ import annotations

from threading import Lock

import numpy as np

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Default batch size for encoding; the model still receives the full list in one
# call and handles internal mini-batching.
DEFAULT_BATCH_SIZE = 32

_model: "SentenceTransformer | None" = None  # noqa: F821 - lazy import type
_model_lock = Lock()


class EmbeddingError(RuntimeError):
    """Raised when loading the model or generating embeddings fails."""


def _model_dim(model: "SentenceTransformer") -> int:  # noqa: F821
    """Return the model's embedding dimension across library versions.

    sentence-transformers 6.0 renamed ``get_sentence_embedding_dimension`` to
    ``get_embedding_dimension``; support both.
    """
    getter = getattr(model, "get_embedding_dimension", None) or (
        model.get_sentence_embedding_dimension
    )
    return int(getter())


def get_embedding_model() -> "SentenceTransformer":  # noqa: F821
    """Load the sentence-transformer model once and reuse it.

    The import is done lazily so that importing this module (e.g. for type
    hints) does not pull in the heavy ``sentence_transformers`` stack until an
    embedding is actually needed.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:  # pragma: no cover - env issue
                    raise EmbeddingError(
                        "sentence-transformers is not installed; run `uv sync`."
                    ) from exc

                model_name = settings.embedding_model
                logger.info("Loading embedding model: %s", model_name)
                try:
                    _model = SentenceTransformer(model_name)
                except Exception as exc:  # noqa: BLE001 - surface any load error
                    raise EmbeddingError(
                        f"Failed to load embedding model '{model_name}': {exc}"
                    ) from exc
                logger.info(
                    "Embedding model loaded (dim=%d)", _model_dim(_model)
                )
    return _model


def embedding_dimension() -> int:
    """Return the model's output embedding dimension (e.g. 384 for MiniLM)."""
    return _model_dim(get_embedding_model())


def embed_texts(
    texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE
) -> np.ndarray:
    """Embed a list of strings into normalized vectors.

    Args:
        texts: The texts to embed.
        batch_size: Encoding batch size passed to the model.

    Returns:
        A ``float32`` array of shape ``(len(texts), dim)``. Each row is
        L2-normalized. For an empty input, returns shape ``(0, dim)``.

    Raises:
        TypeError: If ``texts`` is not a ``list[str]``.
        EmbeddingError: If encoding fails.
    """
    if not isinstance(texts, list):
        raise TypeError(
            f"texts must be a list[str], got {type(texts).__name__}"
        )
    if any(not isinstance(item, str) for item in texts):
        raise TypeError("every item in texts must be a str")

    if not texts:
        return np.empty((0, embedding_dimension()), dtype=np.float32)

    model = get_embedding_model()
    try:
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except Exception as exc:  # noqa: BLE001 - surface any encoding error
        raise EmbeddingError(f"Failed to generate embeddings: {exc}") from exc

    return np.asarray(embeddings, dtype=np.float32)


def embed_text(text: str) -> np.ndarray:
    """Embed a single string into a 1-D normalized vector of shape ``(dim,)``."""
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")
    return embed_texts([text])[0]
