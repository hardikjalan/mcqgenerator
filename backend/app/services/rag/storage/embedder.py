"""
embedder.py
===========
Responsible for calling the OpenAI API to generate embeddings.
"""

from __future__ import annotations

import logging
from openai import OpenAI

from app.services.rag.storage.models import StorageConfig

logger = logging.getLogger(__name__)


class Embedder:
    """Generates embeddings using the OpenAI API."""

    def __init__(self, config: StorageConfig, client: OpenAI | None = None) -> None:
        self.config = config
        # Use provided client or instantiate a default one (expects OPENAI_API_KEY in env)
        self.client = client or OpenAI()

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts in batches.

        Parameters
        ----------
        texts : list[str]
            The list of child chunk texts to embed.

        Returns
        -------
        list[list[float]]
            A list of embedding vectors (each 1536 dimensions for text-embedding-3-small).
        """
        if not texts:
            return []

        embeddings: list[list[float]] = []
        batch_size = self.config.embedding_batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.config.embedding_model,
                    dimensions=self.config.embedding_dimensions,
                )
                
                # OpenAI returns embeddings in the same order as the input
                for data in sorted(response.data, key=lambda x: x.index):
                    embeddings.append(data.embedding)
            except Exception as e:
                logger.error("Error generating embeddings for batch %d: %s", i // batch_size, e)
                raise

        return embeddings
