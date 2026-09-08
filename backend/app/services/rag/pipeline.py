"""
pipeline.py
===========
End-to-End RAG Pipeline Coordinator.

Orchestrates Layers 1 through 5:
1. Downloads uploaded files from Supabase signed URLs via HTTP.
2. Layer 1 Ingestion (IngestionManager) & Layer 2 Cleaning (DocumentCleaner).
3. Layer 3 Chunking (ChunkingManager: hierarchical + semantic + parent-child).
4. Layer 4 Storage & Embeddings (VectorStorageManager + Embedder).
5. Layer 5 Retrieval (RetrievalManager: query embedding + RPC vector match).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from supabase import Client, create_client

from app.schemas import FileItem, GenerateRequest, SourceResult
from app.services.rag.ingestion import IngestionManager
from app.services.rag.chunking import ChunkingManager
from app.services.rag.storage import VectorStorageManager, StorageConfig
from app.services.rag.storage.embedder import Embedder
from app.services.rag.retrieval import RetrievalManager, RetrievalResult
from app.services.rag.generation import MCQGenerator, GeneratedQuestion

logger = logging.getLogger(__name__)


def _get_supabase_client() -> Client:
    """Initialize Supabase client using environment variables."""
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials missing. Please set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in the root-level .env"
        )
    return create_client(url, key)


def _check_gemini_credentials() -> None:
    """Validate that GEMINI_API_KEY is available."""
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        raise RuntimeError(
            "Gemini API key missing. Please set GEMINI_API_KEY in the root-level .env"
        )


class AssessmentRAGPipeline:
    """Coordinates end-to-end processing across RAG Layers 1 to 6."""

    def __init__(
        self,
        supabase_client: Client | None = None,
        embedder: Embedder | None = None,
        mcq_generator: MCQGenerator | None = None,
    ) -> None:
        _check_gemini_credentials()
        self.supabase = supabase_client or _get_supabase_client()
        self.storage_config = StorageConfig()
        self.embedder = embedder or Embedder(config=self.storage_config)

        self.ingestion_manager = IngestionManager()
        self.chunking_manager = ChunkingManager()
        self.storage_manager = VectorStorageManager(
            supabase_client=self.supabase,
            config=self.storage_config,
            embedder=self.embedder,
        )
        self.retrieval_manager = RetrievalManager(
            supabase_client=self.supabase,
            embedder=self.embedder,
        )
        self.mcq_generator = mcq_generator or MCQGenerator()


    def download_file(self, file_item: FileItem) -> bytes:
        """Download raw bytes from a signed Supabase URL."""
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(file_item.signedUrl)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Download failed with HTTP status {resp.status_code}"
                )
            return resp.content

    def process_assessment(
        self, payload: GenerateRequest
    ) -> tuple[list[SourceResult], RetrievalResult | None]:
        """Execute the complete pipeline for the incoming assessment request.

        Returns
        -------
        tuple[list[SourceResult], RetrievalResult | None]
            - Per-file SourceResult objects for the frontend.
            - RetrievalResult containing matched parent contexts for Layer 6.
        """
        sources: list[SourceResult] = []
        successful_source_ids: list[str] = []

        files = payload.files or []
        for file_item in files:
            file_name = file_item.name

            # ── 1. Download file bytes ────────────────────────────────────────
            try:
                content = self.download_file(file_item)
            except Exception as exc:
                logger.error("Download failed for %s: %s", file_name, exc)
                sources.append(
                    SourceResult(
                        name=file_name,
                        ok=False,
                        chars=0,
                        error=f"Download failed: {exc}",
                    )
                )
                continue

            # ── 2. Layer 1 Ingestion & Layer 2 Cleaning ───────────────────────
            try:
                ingest_res = self.ingestion_manager.ingest_bytes(
                    content=content,
                    file_name=file_name,
                )
            except Exception as exc:
                logger.error("Ingestion/cleaning failed for %s: %s", file_name, exc)
                sources.append(
                    SourceResult(
                        name=file_name,
                        ok=False,
                        chars=0,
                        error=f"Extraction failed: {exc}",
                    )
                )
                continue

            if not ingest_res.documents or ingest_res.raw_char_count == 0:
                sources.append(
                    SourceResult(
                        name=file_name,
                        ok=False,
                        chars=0,
                        error="No readable text extracted from document.",
                    )
                )
                continue

            # ── 3. Layer 3 Chunking ───────────────────────────────────────────
            try:
                chunk_res = self.chunking_manager.chunk_documents(ingest_res.documents)
                if not chunk_res.child_chunks:
                    sources.append(
                        SourceResult(
                            name=file_name,
                            ok=False,
                            chars=ingest_res.raw_char_count,
                            error="Document produced no chunks.",
                        )
                    )
                    continue
            except Exception as exc:
                logger.error("Chunking failed for %s: %s", file_name, exc)
                sources.append(
                    SourceResult(
                        name=file_name,
                        ok=False,
                        chars=ingest_res.raw_char_count,
                        error=f"Chunking failed: {exc}",
                    )
                )
                continue

            # ── 4. Layer 4 Embedding & Storage ───────────────────────────────
            try:
                storage_res = self.storage_manager.store_chunks(chunk_res)
                if not storage_res.is_success:
                    err_msg = "; ".join(storage_res.errors)
                    logger.error("Storage failed for %s: %s", file_name, err_msg)
                    sources.append(
                        SourceResult(
                            name=file_name,
                            ok=False,
                            chars=ingest_res.raw_char_count,
                            error=f"Vector storage failed: {err_msg}",
                        )
                    )
                    continue
            except Exception as exc:
                logger.error("Storage/embedding failed for %s: %s", file_name, exc)
                sources.append(
                    SourceResult(
                        name=file_name,
                        ok=False,
                        chars=ingest_res.raw_char_count,
                        error=f"Embedding/storage failed: {exc}",
                    )
                )
                continue

            # Ingestion, chunking, and storage succeeded for this file
            successful_source_ids.append(ingest_res.source_id)
            sources.append(
                SourceResult(
                    name=file_name,
                    ok=True,
                    chars=ingest_res.raw_char_count,
                    error=None,
                )
            )

        # ── 5. Layer 5 Retrieval ──────────────────────────────────────────────
        retrieval_result: RetrievalResult | None = None
        if successful_source_ids:
            try:
                query = RetrievalManager.build_query(
                    subject_name=payload.config.subjectName,
                    topics_covered=payload.config.topicsCovered,
                    learning_objective=payload.config.learningObjective,
                    question_type=payload.config.questionType,
                    source_ids=successful_source_ids,
                )
                retrieval_result = self.retrieval_manager.retrieve(query)

                # ── Temporary Layer 5 Debug Logging ───────────────────────────
                top_parent_scores = [
                    round(ctx.similarity, 4) for ctx in retrieval_result.retrieved_contexts
                ]
                child_scores = [
                    round(c.similarity, 4)
                    for ctx in retrieval_result.retrieved_contexts
                    for c in ctx.matched_children
                ]
                debug_log = (
                    "\n" + "=" * 60 + "\n"
                    "[LAYER 5 RETRIEVAL DEBUG]\n"
                    f"• Query text:\n{retrieval_result.query}\n"
                    f"• Child chunks retrieved: {retrieval_result.total_children_matched}\n"
                    f"• Parent contexts retrieved: {retrieval_result.total_parents_returned}\n"
                    f"• Top parent similarity scores: {top_parent_scores}\n"
                    f"• Top child similarity scores: {child_scores[:5]}\n"
                    + "=" * 60
                )
                logger.info(debug_log)
                print(debug_log)
            except Exception as exc:
                logger.error("Layer 5 Retrieval failed: %s", exc)

        # ── 6. Layer 6 MCQ Generation ──────────────────────────────────────────
        generated_questions: list[GeneratedQuestion] = []
        if retrieval_result and retrieval_result.retrieved_contexts:
            try:
                generated_questions = self.mcq_generator.generate_assessment(
                    contexts=retrieval_result.retrieved_contexts,
                    quiz_config=payload.config,
                )
                logger.info(
                    "Layer 6 Generation complete: %d questions generated.",
                    len(generated_questions),
                )
            except Exception as exc:
                logger.error("Layer 6 Generation failed: %s", exc)
                raise

        return sources, retrieval_result, generated_questions


def run_assessment_pipeline(
    payload: GenerateRequest,
) -> tuple[list[SourceResult], RetrievalResult | None, list[GeneratedQuestion]]:
    """Convenience function to run the full pipeline."""
    pipeline = AssessmentRAGPipeline()
    return pipeline.process_assessment(payload)
