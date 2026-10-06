"""Marking submitted attempts."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.exam.models import ExamAnswer, ExamSection, ExamSectionQuestion
from apps.exam.services import attempts as attempt_service
from apps.exam.tests.base import (
    CourseExamTestCase,
)


class GradingTests(CourseExamTestCase):
    def test_right_wrong_and_skipped(self):
        exam = self.published_exam(questions=3, negative="0.25")
        attempt = attempt_service.start_attempt(exam, self.student)
        right, wrong, _skipped = self.questions
        attempt_service.save_answers(
            attempt,
            [
                {"question_id": right.pk, "option_ids": [self.option(right, 0)]},
                {"question_id": wrong.pk, "option_ids": [self.option(wrong, 2)]},
            ],
        )
        attempt = attempt_service.submit(attempt)
        self.assertEqual((attempt.correct, attempt.wrong, attempt.skipped), (1, 1, 1))
        self.assertEqual(attempt.score, Decimal("0.75"))
        self.assertTrue(attempt.is_official)

    def test_multiple_answer_questions_need_every_right_option(self):
        exam = self.published_exam(questions=1, negative="0")
        section = exam.sections.get()
        block, question = self.mcq(correct=[0, 2], multiple=True)
        ExamSection.objects.filter(pk=section.pk).update(marks=2)
        ExamSectionQuestion.objects.create(section=section, block=block, marks=1, order=9)
        attempt = attempt_service.start_attempt(exam, self.student)
        attempt_service.save_answers(
            attempt, [{"question_id": question.pk, "option_ids": [self.option(question, 0), self.option(question, 2)]}]
        )
        self.assertEqual(attempt_service.submit(attempt).correct, 1)

    def test_the_rate_is_frozen_when_the_attempt_starts(self):
        exam = self.published_exam(questions=1, negative="0.5")
        attempt = attempt_service.start_attempt(exam, self.student)
        ExamSection.objects.filter(exam=exam).update(negative_marks=Decimal("0"))
        q = self.questions[0]
        attempt_service.save_answers(attempt, [{"question_id": q.pk, "option_ids": [self.option(q, 3)]}])
        self.assertEqual(attempt_service.submit(attempt).score, Decimal("-0.5"))

    def test_only_the_first_submitted_attempt_is_official(self):
        exam = self.published_exam(max_attempts=2)
        first = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        second = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        self.assertTrue(first.is_official)
        self.assertFalse(second.is_official)

    def test_regrade_applies_a_corrected_key(self):
        exam = self.published_exam(questions=1, negative="0")
        q = self.questions[0]
        attempt = attempt_service.start_attempt(exam, self.student)
        attempt_service.save_answers(attempt, [{"question_id": q.pk, "option_ids": [self.option(q, 1)]}])
        self.assertEqual(attempt_service.submit(attempt).correct, 0)

        q.options.update(is_correct=False)
        q.options.filter(position=1).update(is_correct=True)
        response = self.client.post(reverse("api:exam:admin_exam_regrade", args=[exam.pk]), **self.admin_auth)
        self.assertEqual(response.json()["regraded"], 1)
        attempt.refresh_from_db()
        self.assertEqual((attempt.correct, attempt.score), (1, Decimal("1")))


class AnswerAnyNTests(CourseExamTestCase):
    """A section of four questions where any two count."""

    def setUp(self):
        super().setUp()
        self.exam = self.published_exam(questions=4, negative="0")
        ExamSection.objects.filter(exam=self.exam).update(required_question_count=2, marks=2)
        self.attempt = attempt_service.start_attempt(self.exam, self.student)

    def answer(self, question, position=0):
        return {"question_id": question.pk, "option_ids": [self.option(question, position)]}

    def test_no_more_than_n_answers_are_taken(self):
        first, second, third, _ = self.questions
        attempt_service.save_answers(self.attempt, [self.answer(first), self.answer(second)])

        with self.assertRaises(ValidationError) as caught:
            attempt_service.save_answers(self.attempt, [self.answer(third)])
        self.assertIn("takes 2 answers", str(caught.exception))
        with self.assertRaises(ValidationError):
            attempt_service.save_answers(self.attempt, [self.answer(q) for q in self.questions])

    def test_an_answer_can_still_change_or_be_swapped_for_another(self):
        first, second, third, _ = self.questions
        attempt_service.save_answers(self.attempt, [self.answer(first), self.answer(second)])

        attempt_service.save_answers(self.attempt, [self.answer(first, 2)])
        attempt_service.save_answers(self.attempt, [{"question_id": second.pk, "option_ids": []}, self.answer(third)])

        attempt = attempt_service.submit(self.attempt)
        self.assertEqual((attempt.correct, attempt.wrong, attempt.skipped), (1, 1, 0))

    def test_answers_past_n_already_stored_are_not_marked(self):
        """Rows saved before the limit existed: only the first two on the paper count."""
        for question in self.questions:
            ExamAnswer.objects.create(
                attempt=self.attempt,
                question=question,
                section_question=ExamSectionQuestion.objects.get(block=question.block),
                selected_option_ids=[self.option(question, 0)],
            )

        attempt = attempt_service.submit(self.attempt)

        self.assertEqual((attempt.correct, attempt.score), (2, Decimal("2")))
        self.assertLessEqual(attempt.score, self.exam.sections.get().marks)

    def test_an_unanswered_required_question_is_skipped_and_the_rest_are_not(self):
        attempt_service.save_answers(self.attempt, [self.answer(self.questions[0])])
        attempt = attempt_service.submit(self.attempt)
        self.assertEqual((attempt.correct, attempt.skipped), (1, 1))


class OneOfficialAttemptTests(CourseExamTestCase):
    def test_the_database_refuses_a_second_official_attempt(self):
        exam = self.published_exam(max_attempts=2)
        first = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        second = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        self.assertTrue(first.is_official)
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(second).objects.filter(pk=second.pk).update(is_official=True)
