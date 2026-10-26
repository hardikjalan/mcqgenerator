import unittest
from unittest.mock import MagicMock
from app.services.rag.generation.models import GeneratedQuestion, Evidence, GeneratedQuiz, ReviewBatch, QuestionReview
from app.services.rag.generation.validation import validate_question
from app.services.rag.generation.generator import MCQGenerator
from app.services.rag.retrieval.models import RetrievedParentContext
from app.schemas import QuizConfig


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.context = RetrievedParentContext(parent_id="parent", source_id="source", content="DNA carries genetic information in cells.", similarity=1,
            metadata={"file_name": "biology.pdf", "page_or_slide_num": 2, "page_numbers": [2]})
        self.question = GeneratedQuestion(id=1, question="Which molecule carries genetic information?", options=["DNA", "Water", "Salt", "Sugar"],
            correct_answer="DNA", explanation="DNA carries genetic information.", topic="Cells", bloom_rationale="Recall a fact.",
            evidence=[Evidence(parent_id="parent", source_id="source", quote="DNA carries genetic information in cells.")])

    def test_valid_evidence_gets_citations_from_extraction_metadata(self):
        self.question.evidence[0].file_name = "invented.pdf"
        self.assertEqual(validate_question(self.question, [self.context]), [])
        self.assertEqual(self.question.evidence[0].file_name, "biology.pdf")
        self.assertEqual(self.question.evidence[0].pages, [2])

    def test_invented_or_wrong_source_evidence_is_rejected(self):
        for patch in ({"quote": "This quotation never appeared in the source."}, {"source_id": "other"}, {"parent_id": "other"}):
            q = self.question.model_copy(deep=True)
            for key, value in patch.items():
                setattr(q.evidence[0], key, value)
            self.assertTrue(validate_question(q, [self.context]))

    def test_malformed_options_and_answer_are_rejected(self):
        for patch in ({"options": ["DNA", "DNA", "Water", "Salt"]}, {"correct_answer": "Not an option"}, {"options": ["DNA"]}, {"evidence": []}):
            q = self.question.model_copy(update=patch, deep=True)
            self.assertTrue(validate_question(q, [self.context]))

    def test_duplicate_questions_and_length_giveaways_are_rejected(self):
        self.assertTrue(validate_question(self.question, [self.context], [self.question]))
        long_answer = " ".join(["answer"] * 30)
        self.question.options[0] = long_answer
        self.question.correct_answer = long_answer
        self.assertTrue(any("length" in e for e in validate_question(self.question, [self.context])))

    def test_independent_verifier_can_reject_syntactically_valid_questions(self):
        generator = MCQGenerator(client=MagicMock())
        generator._call_gemini = MagicMock(return_value=GeneratedQuiz(questions=[self.question]))
        generator.review_questions = MagicMock(return_value=ReviewBatch(reviews=[QuestionReview(id=1, supported=False,
            reason="Answer is unsupported.", bloom_level="Remember", bloom_rationale="Recall", difficulty=1, topic="Cells")]))
        config = QuizConfig(subjectName="Biology", topicsCovered="Cells", learningObjective="Recall", gradeLevel="School", questionType="single", questionCount=1)
        with self.assertRaisesRegex(ValueError, "Only 0 of 1"):
            generator.generate_assessment([self.context], config)
        self.assertEqual(generator.review_questions.call_count, 3)
