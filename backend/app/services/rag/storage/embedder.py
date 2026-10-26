"""
embedder.py
===========
Responsible for calling Google Gemini API to generate embeddings
using gemini-embedding-001.
"""

from __future__ import annotations

import logging
import os
from google import genai
from google.genai import types

from app.services.rag.storage.models import StorageConfig

logger = logging.getLogger(__name__)


class Embedder:
    """Generates embeddings using the Google Gemini API (gemini-embedding-001)."""

    def __init__(self, config: StorageConfig, client: genai.Client | None = None) -> None:
        self.config = config
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if client is not None:
            self.client = client
        elif api_key:
            self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)))
        else:
            self.client = genai.Client(http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)))

    def generate_embeddings(self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        """Generate embeddings for a list of texts in batches.

        Parameters
        ----------
        texts : list[str]
            The list of chunk texts to embed.

        Returns
        -------
        list[list[float]]
            Embedding vectors with the configured output dimensionality.
        """
        if not texts:
            return []

        embeddings: list[list[float]] = []
        batch_size = self.config.embedding_batch_size
        embed_config = types.EmbedContentConfig(
            output_dimensionality=self.config.embedding_dimensions,
            task_type=task_type,
        )

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = self.client.models.embed_content(
                    model=self.config.embedding_model,
                    contents=batch,
                    config=embed_config,
                )
                
                if response.embeddings:
                    for emb in response.embeddings:
                        embeddings.append(list(emb.values))
            except Exception as e:
                logger.error("Error generating Gemini embeddings for batch %d: %s", i // batch_size, e)
                raise

        return embeddings
