"""Authenticated, bounded RAG processing with per-file isolation and topic coverage."""
from __future__ import annotations
import hashlib
import logging
import os
import re
import uuid
from urllib.parse import urlsplit, unquote
import httpx
from llama_index.core.schema import Document
from app.db import get_db
from app.schemas import FileItem, GenerateRequest, SourceResult
from app.services.rag.ingestion import IngestionManager
from app.services.rag.chunking import ChunkingManager
from app.services.rag.processing.cleaning import DocumentCleaner
from app.services.rag.storage import VectorStorageManager, StorageConfig
from app.services.rag.storage.embedder import Embedder
from app.services.rag.retrieval import RetrievalManager, RetrievalResult
from app.services.rag.generation import MCQGenerator, GeneratedQuestion

logger = logging.getLogger(__name__)
MAX_BYTES = 5 * 1024 * 1024

def validate_download_url(url: str, owner_id: str) -> None:
    expected = urlsplit(os.getenv("SUPABASE_URL", ""))
    actual = urlsplit(url)
    path = unquote(actual.path)
    prefix = f"/storage/v1/object/sign/faculty-documents/{owner_id}/"
    if (actual.scheme != "https" or actual.hostname != expected.hostname
            or actual.port not in (None, 443) or actual.username or actual.password
            or actual.fragment or not path.startswith(prefix)
            or any(part in (".", "..") for part in path.split("/"))):
        raise ValueError("Only signed URLs for your own uploaded documents are accepted.")

class AssessmentRAGPipeline:
    def __init__(self, owner_id: str, supabase_client=None, embedder=None, mcq_generator=None):
        self.owner_id = owner_id
        self.supabase = supabase_client or get_db()
        self.storage_config = StorageConfig()
        self.embedder = embedder or Embedder(self.storage_config)
        self.ingestion_manager = IngestionManager()
        self.chunking_manager = ChunkingManager()
        self.storage_manager = VectorStorageManager(self.supabase, config=self.storage_config,
                                                    embedder=self.embedder, owner_id=owner_id)
        self.retrieval_manager = RetrievalManager(self.supabase, embedder=self.embedder)
        self.mcq_generator = mcq_generator or MCQGenerator()

    def download_file(self, file_item: FileItem) -> bytes:
        validate_download_url(file_item.signedUrl, self.owner_id)
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            with client.stream("GET", file_item.signedUrl) as response:
                if response.status_code != 200:
                    raise ValueError("The document link expired or could not be downloaded. Upload it again.")
                data = bytearray()
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data) > MAX_BYTES:
                        raise ValueError("A document exceeds the 5 MB limit.")
                return bytes(data)

    def process_assessment(self, payload: GenerateRequest):
        sources: list[SourceResult] = []
        source_ids: list[str] = []
        batch_bytes = 0
        if payload.sourceType == "text":
            text = (payload.textContent or "").strip()
            if not text:
                raise ValueError("Paste some course material first.")
            source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner_id}:{hashlib.sha256(text.encode()).hexdigest()}"))
            documents = [Document(text=text, metadata={
                "source_id": source_id, "file_name": "Pasted text", "file_type": "text",
                "page_or_slide_num": 1, "total_pages_or_slides": 1,
            })]
            DocumentCleaner().clean_documents(documents)
            items = [("Pasted text", documents, source_id)]
        else:
            if not payload.files or sum(f.size_bytes for f in payload.files) > MAX_BYTES:
                raise ValueError("Upload documents totalling at most 5 MB.")
            items = []
            for item in payload.files:
                try:
                    logger.info("Extracting document: %s", item.name)
                    content = self.download_file(item)
                    batch_bytes += len(content)
                    if batch_bytes > MAX_BYTES:
                        raise ValueError("Combined document size exceeds 5 MB.")
                    ingested = self.ingestion_manager.ingest_bytes(content, item.name, owner_id=self.owner_id)
                    items.append((item.name, ingested.documents, ingested.source_id))
                except Exception as exc:
                    logger.exception("Document extraction failed: %s", item.name)
                    safe_error = str(exc) if isinstance(exc, ValueError) else "This document could not be read. Try a text-based PDF."
                    sources.append(SourceResult(name=item.name, ok=False, chars=0, error=safe_error))
        for name, documents, source_id in items:
            chars = sum(len(d.text) for d in documents)
            try:
                if chars > 500000:
                    raise ValueError("Extracted text exceeds 500,000 characters. Split the document.")
                chunks = self.chunking_manager.chunk_documents(documents)
                logger.info("Indexing %d child chunks for %s", len(chunks.child_chunks), name)
                if not chunks.child_chunks or len(chunks.child_chunks) > 1000:
                    raise ValueError("Document is empty or too large to index in one request.")
                stored = self.storage_manager.store_chunks(chunks)
                if not stored.is_success:
                    logger.error("Indexing failed: %s", stored.errors)
                    raise RuntimeError("Document indexing failed. Please try again.")
                source_ids.append(source_id)
                sources.append(SourceResult(name=name, ok=True, chars=chars))
            except Exception as exc:
                logger.exception("Indexing failed for %s", name)
                sources.append(SourceResult(name=name, ok=False, chars=chars,
                                            error=str(exc) if isinstance(exc, ValueError) else "Document indexing failed. Please try again."))
        if not source_ids:
            raise ValueError("None of the documents could be processed. Check their formats and try again.")
        contexts = {}
        required_contexts = {}
        topics = [t.strip() for t in re.split(r"[,;\n]", payload.config.topicsCovered) if t.strip()]
        if len(topics) > 10:
            raise ValueError("Use up to ten topics in one assessment.")
        for topic in topics:
            logger.info("Retrieving relevant passages for a requested topic")
            query = self.retrieval_manager.build_query(payload.config.subjectName, topic,
                payload.config.learningObjective, source_ids, payload.config.questionType)
            result = self.retrieval_manager.retrieve(query)
            if result.errors:
                logger.error("Retrieval failed: %s", result.errors)
                raise RuntimeError("Source retrieval failed. Please try again.")
            if not result.retrieved_contexts:
                raise ValueError(f"No sufficiently relevant passages were found for topic '{topic[:100]}'. Add material covering it.")
            best = max(result.retrieved_contexts, key=lambda c: c.similarity)
            required_contexts[best.parent_id] = best
            for context in result.retrieved_contexts:
                if context.parent_id not in contexts or context.similarity > contexts[context.parent_id].similarity:
                    contexts[context.parent_id] = context
        selected = list(required_contexts.values())
        extras = sorted((c for key, c in contexts.items() if key not in required_contexts),
                        key=lambda c: c.similarity, reverse=True)
        selected.extend(extras[:16 - len(selected)])
        retrieved = RetrievalResult(query=payload.config.topicsCovered, source_ids=source_ids,
            retrieved_contexts=selected, total_parents_returned=len(selected))
        questions = self.mcq_generator.generate_assessment(selected, payload.config)
        logger.info("Generated %d verified questions", len(questions))
        return sources, retrieved, questions

def run_assessment_pipeline(payload: GenerateRequest, owner_id: str):
    return AssessmentRAGPipeline(owner_id).process_assessment(payload)
