import unittest
from unittest.mock import MagicMock, patch

from app.schemas import QuizConfig
from app.services.rag.generation.generator import MCQGenerator
from app.services.rag.generation.models import GeneratedQuestion, GeneratedQuiz, ReviewBatch, QuestionReview, Evidence
from app.services.rag.retrieval.models import RetrievedParentContext


class TestGenerationModel(unittest.TestCase):
    def test_sdk_does_not_retry_before_application_fallback(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch(
            "app.services.rag.generation.generator.genai.Client"
        ) as client_factory:
            MCQGenerator()
        options = client_factory.call_args.kwargs["http_options"]
        self.assertEqual(options.retry_options.attempts, 1)

    def test_capacity_failure_uses_fallback_with_the_same_schema(self):
        client = MagicMock()
        response = MagicMock()
        response.parsed = GeneratedQuiz(questions=[])
        client.models.generate_content.side_effect = [
            RuntimeError("503 UNAVAILABLE"), response,
        ]
        result = MCQGenerator(client=client)._call_gemini("Generate a quiz.")
        self.assertEqual(result.questions, [])
        calls = client.models.generate_content.call_args_list
        self.assertEqual(calls[0].kwargs["model"], "gemini-3.5-flash-lite")
        self.assertEqual(calls[1].kwargs["model"], "gemini-3.8-flash")
        self.assertIs(calls[1].kwargs["config"].response_schema, GeneratedQuiz)

    def test_non_transient_error_does_not_try_other_models(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("Invalid credentials")
        with self.assertRaisesRegex(RuntimeError, "Invalid credentials"):
            MCQGenerator(client=client)._call_gemini("Generate a quiz.")
        client.models.generate_content.assert_called_once()

    def test_generation_uses_supported_model_and_structured_output(self):
        client = MagicMock()
        client.models.generate_content.return_value.parsed = GeneratedQuiz(questions=[
            GeneratedQuestion(
                id=7, question="What do cells contain?",
                options=["DNA", "Sand", "Plastic", "Glass"], correct_answer="DNA",
                explanation="Cells contain genetic information in DNA.", topic="Cells",
                bloom_rationale="Recall a stated fact.",
                evidence=[Evidence(source_id="source1", parent_id="parent1", quote="Cells contain DNA.")],
            ),
        ])
        generator = MCQGenerator(client=client)
        generator.review_questions = MagicMock(return_value=ReviewBatch(reviews=[QuestionReview(
            id=1, supported=True, reason="Supported by the passage.", bloom_level="Remember",
            bloom_rationale="Recall a fact.", difficulty=1, topic="Cells",
        )]))
        questions = generator.generate_assessment(
            contexts=[RetrievedParentContext(
                parent_id="parent1", source_id="source1",
                content="Cells contain DNA.", similarity=1.0,
            )],
            quiz_config=QuizConfig(
                subjectName="Biology", topicsCovered="Cells",
                learningObjective="Recall cell contents", gradeLevel="School",
                questionType="single", questionCount=1, timeLimit="",
            ),
        )
        call = client.models.generate_content.call_args.kwargs
        self.assertEqual(call["model"], "gemini-3.5-flash-lite")
        self.assertIs(call["config"].response_schema, GeneratedQuiz)
        self.assertEqual(questions[0].id, 1)


if __name__ == "__main__":
    unittest.main()
