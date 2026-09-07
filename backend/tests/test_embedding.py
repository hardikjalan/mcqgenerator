"""
test_embedding.py
=================
The embedding layer: batching, task types, and how failures are treated.

No real API is called — a fake SDK client is injected. What matters here is
the behaviour around the call: that chunks go out in batches sized for the
free tier, that a rate limit is retried but bad input is not, and that a
question and a passage are embedded differently.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.rag.embedding import GeminiEmbedder, get_embedder
from app.services.rag.embedding.base import EmbeddingFailedError


class FakeModels:
    """Records every call; optionally raises a scripted sequence of errors."""

    def __init__(self, errors: list[Exception] | None = None) -> None:
        self.calls: list[dict] = []
        self._errors = list(errors or [])

    def embed_content(self, *, model, contents, config):
        self.calls.append({
            "model": model,
            "contents": list(contents),
            "task": config.task_type,
            "dimensions": config.output_dimensionality,
        })
        if self._errors:
            raise self._errors.pop(0)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * 8) for _ in contents]
        )


def _embedder(errors: list[Exception] | None = None, **kwargs) -> tuple[GeminiEmbedder, FakeModels]:
    embedder = GeminiEmbedder(
        api_key="test-key", model="gemini-embedding-001", dimensions=768, **kwargs
    )
    models = FakeModels(errors)
    embedder._client = SimpleNamespace(models=models)
    return embedder, models


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    """Retries back off by seconds; tests should not actually wait."""
    monkeypatch.setattr("app.services.rag.embedding.gemini.time.sleep", lambda _: None)


# ── Availability ──────────────────────────────────────────────────────────────

def test_no_embedder_without_a_key(monkeypatch):
    """Embeddings are optional: extraction must still work without them."""
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert get_embedder() is None


def test_embedder_uses_the_configured_dimensions(monkeypatch):
    """768 rather than the model default of 3072 — four times as many
    documents fit in Supabase's free tier."""
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    assert get_embedder().dimensions == config.EMBED_DIMENSIONS


# ── Batching ──────────────────────────────────────────────────────────────────

def test_documents_are_sent_in_batches():
    """Free-tier limits are per request, so fewer, larger requests survive
    where one-per-chunk would be throttled."""
    embedder, models = _embedder(batch_size=10)

    vectors = embedder.embed_documents([f"chunk {i}" for i in range(25)])

    assert len(vectors) == 25
    assert [len(call["contents"]) for call in models.calls] == [10, 10, 5]


def test_order_is_preserved_across_batches():
    """A chunk paired with the wrong vector produces a search index that
    returns confidently wrong passages."""
    embedder, models = _embedder(batch_size=2)

    embedder.embed_documents(["a", "b", "c"])

    sent = [text for call in models.calls for text in call["contents"]]
    assert sent == ["a", "b", "c"]


# ── Task types ────────────────────────────────────────────────────────────────

def test_a_question_is_embedded_differently_from_a_passage():
    """The model places a question near the passage that answers it, which is
    not the same as placing two similar passages near each other."""
    embedder, models = _embedder()

    embedder.embed_documents(["a passage of course material"])
    embedder.embed_query("what does this cover?")

    assert models.calls[0]["task"] == "RETRIEVAL_DOCUMENT"
    assert models.calls[1]["task"] == "RETRIEVAL_QUERY"


# ── Failures ──────────────────────────────────────────────────────────────────

def test_a_rate_limit_is_retried():
    """Free-tier quota resets per minute, so a burst refusal is temporary."""
    embedder, models = _embedder(errors=[RuntimeError("429 RESOURCE_EXHAUSTED")])

    vectors = embedder.embed_documents(["chunk"])

    assert len(vectors) == 1
    assert len(models.calls) == 2, "one failure, one successful retry"


def test_bad_input_is_not_retried():
    """Retrying a malformed request wastes the user's time three times over."""
    embedder, models = _embedder(
        errors=[ValueError("400 INVALID_ARGUMENT: bad request")] * 3
    )

    with pytest.raises(EmbeddingFailedError):
        embedder.embed_documents(["chunk"])

    assert len(models.calls) == 1


def test_giving_up_reports_a_user_safe_message():
    embedder, _ = _embedder(errors=[RuntimeError("429 quota")] * 5, max_retries=2)

    with pytest.raises(EmbeddingFailedError) as excinfo:
        embedder.embed_documents(["chunk"])

    assert "try again" in excinfo.value.message.lower()
    assert "429" in (excinfo.value.detail or ""), "the real cause goes to the log"
