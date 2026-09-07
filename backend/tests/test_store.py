"""
test_store.py
=============
The Supabase vector store, against a real HTTP server standing in for
PostgREST.

Mocking httpx would test that the code calls httpx. Serving the requests
proves the actual wire format is right — the upsert header, the delete filter,
the RPC body — which is the part that fails silently against the real thing.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services.rag.store import SupabaseVectorStore
from app.services.rag.store.base import StoredChunk, VectorStoreError

RECORDED: list[dict] = []
RESPONSES: dict[str, tuple[int, object]] = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output clean
        pass

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        path = self.path.split("?")[0]

        RECORDED.append({
            "method": self.command,
            "path": path,
            "query": self.path.split("?")[1] if "?" in self.path else "",
            "headers": dict(self.headers),
            "body": json.loads(raw) if raw else None,
        })

        status, payload = RESPONSES.get(path, (200, []))
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_DELETE = do_GET = _handle


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def store(server):
    RECORDED.clear()
    RESPONSES.clear()
    return SupabaseVectorStore(server, "service-role-key")


def _chunk(n: int = 0) -> StoredChunk:
    return StoredChunk(
        id=f"src-1:{n}",
        source_id="11111111-1111-1111-1111-111111111111",
        file_name="lecture.pdf",
        content=f"chunk {n}",
        chunk_index=n,
        embedding=[0.1] * 8,
        page_start=1,
        page_end=2,
    )


# ── Writing ───────────────────────────────────────────────────────────────────

def test_upsert_sends_rows_and_asks_for_a_merge(store):
    """Without merge-duplicates this is an insert, and re-uploading a file
    fails on the primary key instead of replacing the old chunks."""
    written = store.upsert([_chunk(0), _chunk(1)])

    assert written == 2
    (request,) = RECORDED
    assert request["method"] == "POST"
    assert request["path"] == "/rest/v1/document_chunks"
    assert "merge-duplicates" in request["headers"]["Prefer"]
    assert [row["id"] for row in request["body"]] == ["src-1:0", "src-1:1"]
    assert request["body"][0]["embedding"] == [0.1] * 8


def test_the_service_key_is_sent_both_ways(store):
    """PostgREST wants it as apikey; PostgREST's auth wants it as a bearer."""
    store.upsert([_chunk()])

    headers = RECORDED[0]["headers"]
    assert headers["apikey"] == "service-role-key"
    assert headers["Authorization"] == "Bearer service-role-key"


def test_large_writes_are_split(store):
    """A 768-dimension vector is ~12KB of JSON; a few thousand rows in one
    body is a request PostgREST will refuse."""
    store.upsert([_chunk(n) for n in range(250)])

    assert [len(r["body"]) for r in RECORDED] == [100, 100, 50]


def test_nothing_is_sent_for_an_empty_list(store):
    assert store.upsert([]) == 0
    assert RECORDED == []


def test_delete_filters_by_source(store):
    store.delete_source("11111111-1111-1111-1111-111111111111")

    (request,) = RECORDED
    assert request["method"] == "DELETE"
    assert "source_id=eq.11111111-1111-1111-1111-111111111111" in request["query"]


# ── Searching ─────────────────────────────────────────────────────────────────

def test_search_calls_the_rpc_with_its_scope(store):
    """PostgREST cannot express ordering by vector distance, so similarity
    search goes through the match_chunks function."""
    RESPONSES["/rest/v1/rpc/match_chunks"] = (200, [])

    store.search([0.2] * 8, top_k=5, min_score=0.4, source_ids=["abc"], owner_id="teacher-a")

    (request,) = RECORDED
    assert request["path"] == "/rest/v1/rpc/match_chunks"
    assert request["body"] == {
        "query_embedding": [0.2] * 8,
        "match_count": 5,
        "min_score": 0.4,
        "source_ids": ["abc"],
        "p_owner_id": "teacher-a",
    }


def test_the_owner_filter_is_always_sent(store):
    """Even as None — the SQL treats a missing owner as 'rows with no owner',
    so omitting the key would silently widen the search."""
    RESPONSES["/rest/v1/rpc/match_chunks"] = (200, [])

    store.search([0.2] * 8, top_k=5, min_score=0.4)

    assert "p_owner_id" in RECORDED[0]["body"]


def test_search_maps_rows_to_hits(store):
    RESPONSES["/rest/v1/rpc/match_chunks"] = (200, [{
        "id": "src-1:0",
        "source_id": "11111111-1111-1111-1111-111111111111",
        "file_name": "lecture.pdf",
        "page_start": 3,
        "page_end": 5,
        "chunk_index": 0,
        "content": "Chlorophyll absorbs photons.",
        "metadata": {"x_extraction_method": "ocr"},
        "score": 0.8123,
    }])

    (hit,) = store.search([0.2] * 8, top_k=8, min_score=0.35)

    assert hit.content == "Chlorophyll absorbs photons."
    assert hit.score == pytest.approx(0.8123)
    assert hit.citation() == "lecture.pdf p.3-5"


def test_a_single_page_citation_has_no_range():
    from app.services.rag.store.base import SearchHit

    hit = SearchHit(id="a", source_id="s", file_name="deck.pptx",
                    content="x", score=0.9, page_start=4, page_end=4)
    assert hit.citation() == "deck.pptx p.4"


# ── Failures ──────────────────────────────────────────────────────────────────

def test_a_database_error_is_reported_safely(store):
    """PostgREST puts the real cause in the body — useful in the log, not in
    a message shown to a teacher."""
    RESPONSES["/rest/v1/document_chunks"] = (400, {"message": "column does not exist"})

    with pytest.raises(VectorStoreError) as excinfo:
        store.upsert([_chunk()])

    assert "column does not exist" in (excinfo.value.detail or "")
    assert "column" not in excinfo.value.message
    assert "try again" in excinfo.value.message.lower()


def test_an_unreachable_database_is_reported_safely():
    unreachable = SupabaseVectorStore("http://127.0.0.1:1", "key")

    with pytest.raises(VectorStoreError):
        unreachable.upsert([_chunk()])
