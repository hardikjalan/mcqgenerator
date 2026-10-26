import unittest
from unittest.mock import MagicMock

from app.services.rag.retrieval.service import RetrievalManager
from app.services.rag.storage.models import StorageConfig


class TestRetrievalDimensions(unittest.TestCase):
    def test_below_threshold_matches_never_reach_parent_lookup(self):
        database = MagicMock()
        database.rpc.return_value.execute.return_value.data = [{
            "node_id": "child1", "parent_id": "parent1", "similarity": 0.1,
            "source_id": "source1", "content": "Irrelevant text", "metadata": {},
        }]
        embedder = MagicMock()
        embedder.config = StorageConfig()
        embedder.generate_embeddings.return_value = [[0.1] * 768]
        manager = RetrievalManager(database, embedder=embedder)
        result = manager.retrieve(manager.build_query("Biology", "Cells", "Recall", ["source1"]))
        self.assertEqual(result.errors, [])
        self.assertEqual(result.retrieved_contexts, [])
        database.table.assert_not_called()

    def test_query_uses_the_configured_embedding_dimensions(self):
        for dimensions in (768, 1536):
            with self.subTest(dimensions=dimensions):
                database = MagicMock()
                database.rpc.return_value.execute.return_value.data = []
                embedder = MagicMock()
                embedder.config = StorageConfig(embedding_dimensions=dimensions)
                embedder.generate_embeddings.return_value = [[0.1] * dimensions]
                manager = RetrievalManager(database, embedder=embedder)
                result = manager.retrieve(manager.build_query(
                    subject_name="Biology", topics_covered="Cells",
                    learning_objective="Recall", source_ids=["source1"],
                ))
                self.assertEqual(result.errors, [])
                database.rpc.assert_called_once()
                parameters = database.rpc.call_args.args[1]
                self.assertEqual(len(parameters["query_embedding"]), dimensions)
                self.assertEqual(parameters["filter_source_ids"], ["source1"])


if __name__ == "__main__":
    unittest.main()
