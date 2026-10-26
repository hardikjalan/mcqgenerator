import unittest
from unittest.mock import MagicMock
from types import SimpleNamespace
from app.schemas import GenerateRequest, QuizConfig
from app.services.rag.pipeline import AssessmentRAGPipeline
from app.services.rag.retrieval.models import RetrievedParentContext, RetrievalResult


class TopicCoverageTests(unittest.TestCase):
    def test_context_limit_retains_evidence_for_each_requested_topic(self):
        pipeline = object.__new__(AssessmentRAGPipeline)
        pipeline.owner_id = "teacher"
        pipeline.chunking_manager = MagicMock()
        pipeline.chunking_manager.chunk_documents.return_value = SimpleNamespace(child_chunks=[1])
        pipeline.storage_manager = MagicMock()
        pipeline.storage_manager.store_chunks.return_value = SimpleNamespace(is_success=True)
        pipeline.retrieval_manager = MagicMock()
        first = [RetrievedParentContext(parent_id=f"a-{i}", source_id="source", content="Cells",
                                        similarity=0.99 - i / 1000) for i in range(20)]
        second = RetrievedParentContext(parent_id="b-1", source_id="source", content="Ecology", similarity=0.4)
        pipeline.retrieval_manager.retrieve.side_effect = [
            RetrievalResult(query="Cells", retrieved_contexts=first),
            RetrievalResult(query="Ecology", retrieved_contexts=[second]),
        ]
        pipeline.mcq_generator = MagicMock()
        pipeline.mcq_generator.generate_assessment.return_value = []
        payload = GenerateRequest(sourceType="text", textContent="Cells and ecology are biology topics.",
            config=QuizConfig(subjectName="Biology", topicsCovered="Cells, Ecology", learningObjective="Recall",
                              gradeLevel="School", questionType="single", questionCount=1))
        _, retrieved, _ = pipeline.process_assessment(payload)
        self.assertEqual(len(retrieved.retrieved_contexts), 16)
        self.assertIn("b-1", [c.parent_id for c in retrieved.retrieved_contexts])
