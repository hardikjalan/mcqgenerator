"""
pgvector.py
===========
Vector storage in the Supabase database you already run.

Talks to PostgREST over HTTP rather than opening a Postgres connection. That
keeps ``httpx`` as the only dependency — no database driver, no connection
pool to size, no second set of credentials — and it is the same interface the
rest of the app already uses to reach Supabase.

The one thing PostgREST cannot express is ordering by vector distance, so
similarity search goes through the ``match_chunks`` function defined in
``supabase/migrations/07_chunks.sql``.

Authentication is the service-role key, which bypasses row-level security.
That key must never reach the browser; it is read from the environment
server-side and used nowhere else.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.rag.store.base import (
    SearchHit,
    StoredChunk,
    VectorStoreError,
)

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

# PostgREST rejects very large request bodies, and a 768-dimension vector is
# about 12KB of JSON. 100 rows is roughly a megabyte — comfortably under, and
# few enough that a retry costs little.
_WRITE_BATCH = 100


class SupabaseVectorStore:
    """``document_chunks`` in Supabase, reached through PostgREST."""

    name = "supabase-pgvector"

    def __init__(self, url: str, service_key: str, *, table: str = "document_chunks") -> None:
        self._base = f"{url}/rest/v1"
        self._table = table
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    # ── Writing ───────────────────────────────────────────────────────────

    def upsert(self, chunks: list[StoredChunk]) -> int:
        """Insert chunks, replacing any that already exist with the same id.

        Chunk ids are deterministic (``<source_id>:<n>``), so re-uploading a
        file overwrites its chunks rather than storing the document twice.
        """
        if not chunks:
            return 0

        written = 0
        for start in range(0, len(chunks), _WRITE_BATCH):
            batch = chunks[start : start + _WRITE_BATCH]
            self._request(
                "POST",
                f"/{self._table}",
                json=[_to_row(chunk) for chunk in batch],
                # merge-duplicates is what turns this insert into an upsert.
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            written += len(batch)

        return written

    def delete_source(self, source_id: str) -> None:
        """Remove every chunk from one uploaded file."""
        self._request(
            "DELETE",
            f"/{self._table}",
            params={"source_id": f"eq.{source_id}"},
            headers={"Prefer": "return=minimal"},
        )

    # ── Reading ───────────────────────────────────────────────────────────

    def search(
        self,
        embedding: list[float],
        *,
        top_k: int,
        min_score: float,
        source_ids: list[str] | None = None,
        owner_id: str | None = None,
    ) -> list[SearchHit]:
        """Return the closest chunks, nearest first.

        The owner filter is applied inside ``match_chunks`` rather than here,
        so it cannot be forgotten by a caller or dropped by a later refactor
        of this method.
        """
        response = self._request(
            "POST",
            "/rpc/match_chunks",
            json={
                "query_embedding": embedding,
                "match_count": top_k,
                "min_score": min_score,
                "source_ids": source_ids,
                "p_owner_id": owner_id,
            },
        )

        return [_to_hit(row) for row in (response or [])]

    # ── Internal ──────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                response = client.request(
                    method,
                    f"{self._base}{path}",
                    json=json,
                    params=params,
                    headers={**self._headers, **(headers or {})},
                )
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code >= 400:
            # PostgREST puts the real cause in the body; it is for the log.
            raise VectorStoreError(
                f"{method} {path} -> {response.status_code}: {response.text[:400]}"
            )

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError:
            return None


# ── Row mapping ───────────────────────────────────────────────────────────────

def _to_row(chunk: StoredChunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "source_id": chunk.source_id,
        "owner_id": chunk.owner_id,
        "file_name": chunk.file_name,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "metadata": chunk.metadata,
        "embedding": chunk.embedding,
    }


def _to_hit(row: dict[str, Any]) -> SearchHit:
    return SearchHit(
        id=row["id"],
        source_id=str(row["source_id"]),
        file_name=row["file_name"],
        content=row["content"],
        score=float(row.get("score", 0.0)),
        page_start=row.get("page_start"),
        page_end=row.get("page_end"),
        metadata=row.get("metadata") or {},
    )
