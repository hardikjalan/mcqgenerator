"""
test_api.py
===========
End to end through the real route: a real HTTP download of a real PDF,
parsed by the real pipeline. No mocks.

A throwaway local HTTP server stands in for Supabase storage, so the
``fetcher`` module is genuinely exercised — signed URLs are just URLs.
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.main import app

CONFIG = {
    "subjectName": "Biology",
    "topicsCovered": "Photosynthesis",
    "learningObjective": "Understand light reactions",
    "gradeLevel": "Undergraduate",
    "questionType": "mcq",
    "questionCount": 5,
    "timeLimit": "20",
}


@pytest.fixture(scope="module")
def file_server():
    """Serve tests/fixtures/ on a random port for the duration of the module."""
    from pathlib import Path

    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent / "fixtures"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/").json() == {"status": "ok"}


def test_limits_are_served_not_hardcoded(client):
    """The frontend used to hardcode these, with a comment in each file asking
    the next person to keep the others in sync."""
    body = client.get("/limits").json()

    assert body["maxFileBytes"] == 5 * 1024 * 1024
    assert ".pdf" in body["allowedExtensions"]
    assert isinstance(body["ocrEnabled"], bool)


def test_limits_report_whether_ocr_is_available(client, monkeypatch):
    """So the upload widget can stop offering image formats on a deployment
    that cannot read them."""
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert client.get("/limits").json()["ocrEnabled"] is False

    monkeypatch.setattr(config, "GEMINI_API_KEY", "a-key")
    assert client.get("/limits").json()["ocrEnabled"] is True


def test_upload_is_extracted_end_to_end(client, file_server):
    """The 501 this replaced is the whole point of the change."""
    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{
            "name": "sample.pdf",
            "signedUrl": f"{file_server}/sample.pdf",
            "size_bytes": 2702,
        }],
    })

    assert response.status_code == 200
    (source,) = response.json()["sources"]
    assert source["name"] == "sample.pdf"
    assert source["ok"] is True
    assert source["error"] is None
    assert source["chars"] > 100
    assert source["chunks"] >= 1, "extraction must produce retrievable chunks"


def test_a_dead_link_fails_only_its_own_row(client, file_server):
    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [
            {"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702},
            {"name": "missing.pdf", "signedUrl": f"{file_server}/missing.pdf", "size_bytes": 1000},
        ],
    })

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert [s["ok"] for s in sources] == [True, False]
    assert "expired" in sources[1]["error"]


def test_extracted_text_is_not_sent_to_the_browser(client, file_server):
    """SourceResult carries a character count, never the document text."""
    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702}],
    })

    assert "Photosynthesis" not in response.text


def test_text_source_still_works(client):
    response = client.post("/generate-assessment", json={
        "sourceType": "text",
        "textContent": "  Chlorophyll absorbs light.  ",
        "config": CONFIG,
    })

    (source,) = response.json()["sources"]
    assert source["ok"] and source["chars"] == len("Chlorophyll absorbs light.")


def test_empty_requests_are_refused(client):
    blank = client.post("/generate-assessment", json={
        "sourceType": "text", "textContent": "   ", "config": CONFIG,
    })
    assert blank.status_code == 400
    assert blank.json() == {"error": "No text was provided."}

    no_files = client.post("/generate-assessment", json={
        "sourceType": "upload", "files": [], "config": CONFIG,
    })
    assert no_files.status_code == 400


def test_a_malformed_request_returns_one_sentence(client):
    """FastAPI's default validation body is a list of objects, which the
    dashboard would render as [object Object]."""
    response = client.post("/generate-assessment", json={"sourceType": "upload"})

    assert response.status_code == 422
    assert isinstance(response.json()["error"], str)


# ── Search ────────────────────────────────────────────────────────────────────

def test_search_refuses_an_unscoped_query(client):
    """An unscoped search would range over every document ever uploaded, by
    anyone — a data leak dressed up as a convenience."""
    response = client.post("/search", json={"question": "photosynthesis", "sourceIds": []})

    assert response.status_code == 400
    assert "documents" in response.json()["error"]


def test_search_refuses_an_empty_question(client):
    response = client.post("/search", json={"question": "   ", "sourceIds": ["abc"]})

    assert response.status_code == 400


def test_search_says_so_when_it_is_not_set_up(client, monkeypatch):
    """Different from 'found nothing'. A deployment with no key returns 503,
    not an empty list that reads like the material is missing."""
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    response = client.post("/search", json={"question": "q", "sourceIds": ["abc"]})

    assert response.status_code == 503
    assert "isn't set up" in response.json()["error"]


def test_search_returns_hits_with_citations(client, monkeypatch):
    from app.services.rag.store.base import SearchHit
    import app.routes as routes

    class FakeRetriever:
        available = True

        def search(self, question, *, source_ids=None, owner_id=None, top_k=None):
            return [SearchHit(
                id="s:0", source_id="s", file_name="lecture.pdf",
                content="Chlorophyll absorbs photons.", score=0.812345,
                page_start=3, page_end=5,
            )]

    monkeypatch.setattr(routes, "Retriever", lambda: FakeRetriever())

    response = client.post("/search", json={"question": "light", "sourceIds": ["s"]})

    (hit,) = response.json()["hits"]
    assert hit["citation"] == "lecture.pdf p.3-5"
    assert hit["score"] == 0.8123, "rounded for display"


def test_extraction_reports_whether_a_file_was_indexed(client, file_server):
    """'Read but not searchable' is a real state and the dashboard needs to
    be able to say so."""
    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702}],
    })

    (source,) = response.json()["sources"]
    assert source["ok"] is True
    assert source["indexed"] is False, "no key configured in the test environment"
    assert source["indexNote"]
    assert source["sourceId"], "the client needs this to scope a later search"


# ── Authentication ────────────────────────────────────────────────────────────

def test_uploads_require_a_signed_in_user_once_supabase_exists(client, monkeypatch, file_server):
    """With two faculty members and no authentication, every upload lands in
    one shared anonymous pool."""
    from app import auth, config

    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    auth._cache.clear()

    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702}],
    })

    assert response.status_code == 401


def test_search_requires_a_signed_in_user(client, monkeypatch):
    from app import auth, config

    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    auth._cache.clear()

    response = client.post("/search", json={"question": "q", "sourceIds": ["abc"]})

    assert response.status_code == 401


def test_local_development_stays_open(client, file_server):
    """No Supabase project means nothing to protect, and demanding a token
    would make the API unusable while building."""
    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702}],
    })

    assert response.status_code == 200


# ── Generation ────────────────────────────────────────────────────────────────

def test_no_generator_configured_says_so_without_failing_the_upload(client, file_server):
    """The files were still read, chunked and indexed. Returning an error here
    would tell the teacher their upload failed when it did not."""
    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702}],
    })

    body = response.json()
    assert response.status_code == 200
    assert body["sources"][0]["ok"] is True
    assert body["questions"] == []
    assert "isn't switched on" in body["note"]


def test_questions_come_back_with_their_evidence(client, file_server, monkeypatch):
    """A question a teacher cannot trace back to their own material is a
    question they have no reason to trust."""
    import app.routes as routes
    from app.services.quiz import QuizResult
    from app.services.rag.generation import MCQ

    def fake_quiz(brief, **kwargs):
        return QuizResult(questions=[MCQ(
            question="Where does chlorophyll absorb photons?",
            options=["Thylakoid membrane", "Stroma", "Cell wall", "Nucleus"],
            correct_index=0,
            explanation="Stated in the passage.",
            citations=["Chlorophyll absorbs photons in the thylakoid membrane"],
        )])

    monkeypatch.setattr(routes, "generate_quiz", fake_quiz)

    response = client.post("/generate-assessment", json={
        "sourceType": "upload",
        "config": CONFIG,
        "files": [{"name": "sample.pdf", "signedUrl": f"{file_server}/sample.pdf", "size_bytes": 2702}],
    })

    (question,) = response.json()["questions"]
    assert question["correctIndex"] == 0
    assert len(question["options"]) == 4
    assert question["evidence"]
