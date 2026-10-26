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
        
        # Create mock data objects matching Google GenAI embed_content structure
        mock_emb1 = MagicMock()
        mock_emb1.values = [0.1] * 768
        
        mock_emb2 = MagicMock()
        mock_emb2.values = [0.2] * 768
        
        mock_embedding_response.embeddings = [mock_emb1, mock_emb2]
        self.mock_client.models.embed_content.return_value = mock_embedding_response
        
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
        self.mock_client.models.embed_content.assert_called_once()
        call_kwargs = self.mock_client.models.embed_content.call_args.kwargs
        self.assertEqual(call_kwargs["contents"], ["Chunk 1", "Chunk 2"])
        self.assertEqual(call_kwargs["model"], "gemini-embedding-001")
        self.assertEqual(call_kwargs["config"].output_dimensionality, 768)
        
        # Verify Supabase was called with correct data
        upsert_call_args = self.mock_supabase.table().upsert.call_args[0][0]
        self.assertEqual(len(upsert_call_args), 2)
        
        self.assertEqual(upsert_call_args[0]["node_id"], "node1")
        self.assertEqual(upsert_call_args[0]["content"], "Chunk 1")
        self.assertEqual(upsert_call_args[0]["source_id"], "source1")
        self.assertEqual(len(upsert_call_args[0]["embedding"]), 768)

    def test_parent_and_child_rows_satisfy_legacy_columns(self):
        parent = TextNode(text="Parent context", id_="parent1", metadata={
            "file_name": "notes.pdf", "page_numbers": [2, 3],
        })
        children = [TextNode(text=f"Child {i}", id_=f"child{i}", metadata={
            "parent_id": "parent1", "chunk_index": i, "page_or_slide_num": 2,
        }) for i in (1, 2)]
        result = self.service.store_chunks(ChunkingResult(
            source_id="source1", file_name="notes.pdf",
            parent_chunks=[parent], child_chunks=children,
        ))
        self.assertTrue(result.is_success)
        rows = self.mock_supabase.table().upsert.call_args.args[0]
        self.assertIsNone(rows[0]["embedding"])
        self.assertIsNone(rows[0]["parent_id"])
        self.assertEqual((rows[0]["page_start"], rows[0]["page_end"]), (2, 3))
        for index, row in enumerate(rows):
            self.assertEqual(row["file_name"], "notes.pdf")
            self.assertEqual(row["chunk_index"], index)
        self.assertEqual(rows[1]["parent_id"], "parent1")

    def test_owned_upload_uses_atomic_source_replacement(self):
        self.service.owner_id = "teacher-id"
        self.mock_supabase.rpc.return_value.execute.return_value.data = 2
        parent = TextNode(text="Parent", id_="parent1")
        child = TextNode(text="Child", id_="child1", metadata={"parent_id": "parent1"})
        self.embedder.generate_embeddings = MagicMock(return_value=[[0.1] * 768])
        self.mock_supabase.reset_mock()
        result = self.service.store_chunks(ChunkingResult(source_id="source1", parent_chunks=[parent], child_chunks=[child]))
        self.assertTrue(result.is_success)
        self.assertEqual(result.chunks_inserted, 2)
        name, parameters = self.mock_supabase.rpc.call_args.args
        self.assertEqual(name, "replace_document_chunks")
        self.assertEqual(parameters["p_owner_id"], "teacher-id")
        self.assertEqual(parameters["p_source_id"], "source1")
        self.assertEqual(len(parameters["p_rows"]), 2)
        self.mock_supabase.table.assert_not_called()

    def test_wrong_embedding_dimension_does_not_write(self):
        self.embedder.generate_embeddings = MagicMock(return_value=[[0.1] * 1536])
        self.mock_supabase.reset_mock()
        result = self.service.store_chunks(ChunkingResult(
            child_chunks=[TextNode(text="Child")],
        ))
        self.assertFalse(result.is_success)
        self.assertIn("768-dimensional", result.errors[0])
        self.mock_supabase.table.assert_not_called()


if __name__ == '__main__':
    unittest.main()
