"""
test_retrieval.py
=================
The join between the embedder and the store — indexing and searching.

Both halves are faked. What is under test is the wiring: that chunks are
paired with the right vectors, that a re-upload replaces rather than
duplicates, that a search is scoped, and that an indexing failure does not
destroy an otherwise successful upload.
"""

from __future__ import annotations

import pytest
from llama_index.core.schema import TextNode

from app.services.rag.embedding.base import EmbeddingFailedError, EmbeddingUnavailableError
from app.services.rag.retrieval import Retriever
from app.services.rag.store.base import SearchHit, VectorStoreUnavailableError

SOURCE = "11111111-1111-1111-1111-111111111111"


class FakeEmbedder:
    name = "fake"
    dimensions = 8

    def __init__(self, *, fail: bool = False, short: bool = False) -> None:
        self.fail = fail
        self.short = short
        self.queries: list[str] = []

    def embed_documents(self, texts):
        if self.fail:
            raise EmbeddingFailedError("the API is having a bad minute")
        vectors = [[float(i)] * 8 for i in range(len(texts))]
        return vectors[:-1] if self.short else vectors

    def embed_query(self, text):
        self.queries.append(text)
        return [0.5] * 8


class FakeStore:
    name = "fake"

    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.rows: list = []
        self.deleted: list[str] = []
        self.searches: list[dict] = []
        self._hits = hits or []

    def upsert(self, chunks):
        self.rows.extend(chunks)
        return len(chunks)

    def delete_source(self, source_id):
        self.deleted.append(source_id)

    def search(self, embedding, *, top_k, min_score, source_ids=None, owner_id=None):
        self.searches.append({
            "embedding": embedding, "top_k": top_k, "min_score": min_score,
            "source_ids": source_ids, "owner_id": owner_id,
        })
        return self._hits


def _chunks(n: int = 3) -> list[TextNode]:
    nodes = []
    for i in range(n):
        node = TextNode(
            text=f"chunk {i}",
            metadata={
                "source_id": SOURCE,
                "file_name": "lecture.pdf",
                "chunk_index": i,
                "page_start": i + 1,
                "page_end": i + 1,
            },
        )
        node.id_ = f"{SOURCE}:{i}"
        nodes.append(node)
    return nodes


# ── Availability ──────────────────────────────────────────────────────────────

def test_unavailable_when_either_half_is_missing():
    assert Retriever(embedder=FakeEmbedder(), store=None).available is False
    assert Retriever(embedder=None, store=FakeStore()).available is False
    assert Retriever(embedder=FakeEmbedder(), store=FakeStore()).available is True


def test_indexing_without_a_provider_says_so():
    with pytest.raises(EmbeddingUnavailableError):
        Retriever(embedder=None, store=FakeStore()).index(_chunks())

    with pytest.raises(VectorStoreUnavailableError):
        Retriever(embedder=FakeEmbedder(), store=None).index(_chunks())


# ── Indexing ──────────────────────────────────────────────────────────────────

def test_chunks_are_stored_with_their_vectors_and_origin():
    store = FakeStore()

    written = Retriever(embedder=FakeEmbedder(), store=store).index(
        _chunks(2), owner_id="user-9"
    )

    assert written == 2
    first = store.rows[0]
    assert first.id == f"{SOURCE}:0"
    assert first.content == "chunk 0"
    assert first.file_name == "lecture.pdf"
    assert first.owner_id == "user-9"
    assert first.embedding == [0.0] * 8


def test_a_reupload_clears_the_old_chunks_first():
    """Deterministic ids overwrite, but a document that got *shorter* would
    otherwise leave the extra chunks from last time behind, and they would
    keep being retrieved."""
    store = FakeStore()

    Retriever(embedder=FakeEmbedder(), store=store).index(_chunks())

    assert store.deleted == [SOURCE]


def test_a_vector_count_mismatch_is_refused():
    """Silently pairing chunks with the wrong embeddings produces a search
    index that returns confidently wrong passages — worse than an error."""
    with pytest.raises(ValueError):
        Retriever(embedder=FakeEmbedder(short=True), store=FakeStore()).index(_chunks())


def test_nothing_to_index_is_not_an_error():
    assert Retriever(embedder=FakeEmbedder(), store=FakeStore()).index([]) == 0


# ── Searching ─────────────────────────────────────────────────────────────────

def test_a_search_is_scoped_to_the_given_sources():
    """Unscoped, a search ranges over every document ever uploaded by anyone."""
    store = FakeStore()

    Retriever(embedder=FakeEmbedder(), store=store).search(
        "how do plants make food?", source_ids=[SOURCE]
    )

    assert store.searches[0]["source_ids"] == [SOURCE]


def test_a_search_is_scoped_to_the_owner():
    """The security fence, as opposed to the usefulness one: source ids come
    from the client, the owner comes from a verified token."""
    store = FakeStore()

    Retriever(embedder=FakeEmbedder(), store=store).search(
        "q", source_ids=[SOURCE], owner_id="teacher-a"
    )

    assert store.searches[0]["owner_id"] == "teacher-a"


def test_search_defaults_come_from_config():
    from app import config

    store = FakeStore()
    Retriever(embedder=FakeEmbedder(), store=store).search("q", source_ids=[SOURCE])

    assert store.searches[0]["top_k"] == config.RETRIEVAL_TOP_K
    assert store.searches[0]["min_score"] == config.RETRIEVAL_MIN_SCORE


def test_the_question_is_embedded_not_the_documents():
    embedder = FakeEmbedder()

    Retriever(embedder=embedder, store=FakeStore()).search("what is a Punnett square?")

    assert embedder.queries == ["what is a Punnett square?"]


def test_hits_come_back_with_citations():
    hit = SearchHit(id="a", source_id=SOURCE, file_name="deck.pptx",
                    content="Alleles segregate.", score=0.77,
                    page_start=1, page_end=3)

    (result,) = Retriever(embedder=FakeEmbedder(), store=FakeStore([hit])).search("q")

    assert result.citation() == "deck.pptx p.1-3"


# ── Failure is contained ──────────────────────────────────────────────────────

def test_an_indexing_failure_does_not_lose_the_extraction(serve, pdf_path, monkeypatch):
    """The file was downloaded, parsed and chunked before indexing was tried.
    Failing the upload at this point would throw all of that away and tell the
    user their file was bad, which is not what happened."""
    from app.services import extraction

    serve({"sample.pdf": pdf_path.read_bytes()})

    (result,) = extraction.extract_sources(
        [extraction.SourceInput("sample.pdf", "https://example.test/x", 2702)],
        retriever=Retriever(embedder=FakeEmbedder(fail=True), store=FakeStore()),
    )

    assert result.ok is True, "extraction succeeded even though indexing did not"
    assert result.chunks
    assert result.indexed is False
    assert "try again" in result.index_note.lower()


def test_unconfigured_search_is_reported_not_hidden(serve, pdf_path):
    """A file that was read but not indexed is a different state from a file
    that failed, and the response has to distinguish them."""
    from app.services import extraction

    serve({"sample.pdf": pdf_path.read_bytes()})

    (result,) = extraction.extract_sources(
        [extraction.SourceInput("sample.pdf", "https://example.test/x", 2702)],
        retriever=Retriever(embedder=None, store=None),
    )

    assert result.ok is True
    assert result.indexed is False
    assert "isn't configured" in result.index_note
