import sys
import unittest
from unittest.mock import MagicMock, patch

from llama_index.core.schema import TextNode

from app.services.rag.chunking.models import ChunkingResult
from app.services.rag.storage.models import StorageConfig, StorageResult
from app.services.rag.storage.embedder import Embedder
from app.services.rag.storage.service import VectorStorageManager

class TestLayer4Storage(unittest.TestCase):
    def setUp(self):
        self.mock_supabase = MagicMock()
        self.mock_supabase.table().upsert().execute.return_value = MagicMock(data=[1, 2])
        
        self.mock_client = MagicMock()
        mock_embedding_response = MagicMock()
        
        # Create mock data objects matching OpenAI's response structure
        mock_data1 = MagicMock()
        mock_data1.index = 0
        mock_data1.embedding = [0.1] * 1536
        
        mock_data2 = MagicMock()
        mock_data2.index = 1
        mock_data2.embedding = [0.2] * 1536
        
        mock_embedding_response.data = [mock_data1, mock_data2]
        self.mock_client.embeddings.create.return_value = mock_embedding_response
        
        config = StorageConfig()
        self.embedder = Embedder(config=config, client=self.mock_client)
        self.service = VectorStorageManager(
            supabase_client=self.mock_supabase,
            config=config,
            embedder=self.embedder
        )
        
    def test_store_chunks(self):
        # Create test nodes
        node1 = TextNode(text="Chunk 1", id_="node1", metadata={"parent_id": "parent1", "page_or_slide_num": 1})
        node2 = TextNode(text="Chunk 2", id_="node2", metadata={"parent_id": "parent1", "page_or_slide_num": 1})
        
        chunking_result = ChunkingResult(
            source_id="source1",
            child_chunks=[node1, node2]
        )
        
        result = self.service.store_chunks(chunking_result)
        
        # Verify success
        self.assertTrue(result.is_success)
        self.assertEqual(result.chunks_inserted, 2)
        
        # Verify embeddings were called
        self.mock_client.embeddings.create.assert_called_once_with(
            input=["Chunk 1", "Chunk 2"],
            model="text-embedding-3-small",
            dimensions=1536
        )
        
        # Verify Supabase was called with correct data
        upsert_call_args = self.mock_supabase.table().upsert.call_args[0][0]
        self.assertEqual(len(upsert_call_args), 2)
        
        self.assertEqual(upsert_call_args[0]["node_id"], "node1")
        self.assertEqual(upsert_call_args[0]["content"], "Chunk 1")
        self.assertEqual(upsert_call_args[0]["source_id"], "source1")
        self.assertEqual(len(upsert_call_args[0]["embedding"]), 1536)
        
if __name__ == '__main__':
    unittest.main()
