"""
gemini.py
=========
Embeddings via Google's ``gemini-embedding-001``.

Free on Google's unpaid quota, which is what this project runs on by default.
Two consequences of that shape the code:

* **Rate limits are per minute**, so a burst of requests is refused outright
  rather than queued. Chunks are therefore sent in batches, and a refusal is
  retried with a growing pause rather than surfaced immediately.
* **Content on the unpaid quota is used by Google to improve its products**
  and may be read by human reviewers (their API terms). Enabling billing on
  the same key changes that without any code change here.

Output dimensions are set explicitly rather than left at the model default —
see ``EMBED_DIMENSIONS`` in config for why 768 rather than 3072.
"""

from __future__ import annotations

import time

from app import config
from app.services.rag.embedding.base import EmbeddingFailedError


class GeminiEmbedder:
    """Embeddings backed by the ``google-genai`` SDK."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        *,
        batch_size: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self.dimensions = dimensions
        self._batch_size = batch_size or config.EMBED_BATCH_SIZE
        self._max_retries = max_retries or config.EMBED_MAX_RETRIES
        self._client = None  # built lazily; constructing it costs a handshake

    # ── Public API ────────────────────────────────────────────────────────

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunks for storage, in batches, preserving order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._embed(batch, task="RETRIEVAL_DOCUMENT"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query.

        The task type differs from ``embed_documents`` on purpose: the model
        places a question and the passage that answers it near each other,
        which is not the same as placing two similar passages near each other.
        """
        (vector,) = self._embed([text], task="RETRIEVAL_QUERY")
        return vector

    # ── Internal ──────────────────────────────────────────────────────────

    def _embed(self, texts: list[str], *, task: str) -> list[list[float]]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise EmbeddingFailedError("google-genai is not installed") from exc

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = self._client.models.embed_content(
                    model=self._model,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        task_type=task,
                        output_dimensionality=self.dimensions,
                    ),
                )
                return [list(item.values) for item in response.embeddings]

            except Exception as exc:  # noqa: BLE001 - SDK raises many types
                last_error = exc
                if not _is_retryable(exc) or attempt == self._max_retries - 1:
                    break
                # Quota resets on a per-minute window, so back off rather than
                # hammering: 2s, 4s, 8s.
                time.sleep(2 ** (attempt + 1))

        raise EmbeddingFailedError(f"{type(last_error).__name__}: {last_error}")


def _is_retryable(exc: Exception) -> bool:
    """True for rate limits and transient server errors, false for bad input.

    Retrying a malformed request just wastes the user's time three times over.
    """
    text = f"{type(exc).__name__} {exc}".lower()
    return any(
        marker in text
        for marker in ("429", "resource_exhausted", "rate limit", "quota",
                       "503", "unavailable", "500", "internal", "timeout")
    )
