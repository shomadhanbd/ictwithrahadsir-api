"""A student starting, answering and closing an attempt."""

from django.utils import timezone

from apps.core.testing import bearer, make_user
from apps.courses.models import Content, ContentCompletion, Course, Enrollment
from apps.exam.models import ExamAttempt, ExamSection
from apps.exam.services import attempts as attempt_service
from apps.exam.tests.base import (
    CourseExamTestCase,
    url,
)


class TakingAnExamTests(CourseExamTestCase):
    def test_not_enrolled_is_refused(self):
        exam = self.published_exam()
        response = self.client.post(url("exam_start", exam.pk), **bearer(make_user()))
        self.assertEqual(response.status_code, 403)

    def test_a_draft_exam_is_not_found(self):
        exam = self.lesson().exam
        self.assertEqual(self.client.get(url("exam_detail", exam.pk), **self.student_auth).status_code, 404)

    def test_outside_the_window_is_refused(self):
        exam = self.published_exam(start_time=timezone.now() + timezone.timedelta(hours=1))
        response = self.client.post(url("exam_start", exam.pk), **self.student_auth)
        self.assertEqual(response.status_code, 422)

    def test_an_unreleased_exam_lesson_cannot_be_started(self):
        exam = self.published_exam()
        Content.objects.filter(pk=exam.lesson_id).update(available_from=timezone.now() + timezone.timedelta(days=1))
        response = self.client.post(url("exam_start", exam.pk), **self.student_auth)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Available from", response.json()["message"])

    def test_starting_twice_resumes(self):
        exam = self.published_exam()
        first = self.client.post(url("exam_start", exam.pk), **self.student_auth).json()["id"]
        second = self.client.post(url("exam_start", exam.pk), **self.student_auth).json()["id"]
        self.assertEqual(first, second)

    def test_submitting_completes_the_lesson(self):
        exam = self.published_exam()
        attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        self.assertTrue(ContentCompletion.objects.filter(user=self.student, content_id=exam.lesson_id).exists())

    def test_attempts_are_limited(self):
        exam = self.published_exam()
        attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        response = self.client.post(url("exam_start", exam.pk), **self.student_auth)
        self.assertEqual(response.status_code, 422)

    def test_the_paper_carries_no_answer_key(self):
        exam = self.published_exam()
        attempt = attempt_service.start_attempt(exam, self.student)
        body = self.client.get(url("attempt_detail", attempt.pk), **self.student_auth).content.decode()
        for secret in ("is_correct", "explanation", "Because."):
            self.assertNotIn(secret, body)

    def test_answers_save_and_are_returned(self):
        exam = self.published_exam()
        attempt = attempt_service.start_attempt(exam, self.student)
        q = self.questions[0]
        response = self.client.put(
            url("attempt_answers", attempt.pk),
            {"answers": [{"question_id": q.pk, "option_ids": [self.option(q, 1)]}]},
            format="json",
            **self.student_auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        saved = self.client.get(url("attempt_detail", attempt.pk), **self.student_auth).json()["answers"]
        self.assertEqual(saved, [{"question_id": q.pk, "option_ids": [self.option(q, 1)]}])

    def test_losing_access_mid_attempt_submits_it(self):
        """Not left open but unable to save: the answers so far are marked, and the page is told it is over."""
        exam = self.published_exam()
        attempt = attempt_service.start_attempt(exam, self.student)
        q = self.questions[0]
        attempt_service.save_answers(attempt, [{"question_id": q.pk, "option_ids": [self.option(q, 0)]}])
        Enrollment.objects.filter(user=self.student).delete()

        response = self.client.put(
            url("attempt_answers", attempt.pk),
            {"answers": [{"question_id": q.pk, "option_ids": [self.option(q, 1)]}]},
            format="json",
            **self.student_auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("attempt", response.json()["errors"])
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.correct), (ExamAttempt.Status.SUBMITTED, 1))

    def test_a_closed_attempt_and_a_refused_answer_are_told_apart(self):
        """The page closes the paper only for `attempt`; an answer it may not save comes back under `answers`."""
        exam = self.published_exam(questions=3)
        ExamSection.objects.filter(exam=exam).update(required_question_count=1, marks=1)
        attempt = attempt_service.start_attempt(exam, self.student)
        first, second = self.questions[0], self.questions[1]

        def save(question):
            return self.client.put(
                url("attempt_answers", attempt.pk),
                {"answers": [{"question_id": question.pk, "option_ids": [self.option(question, 0)]}]},
                format="json",
                **self.student_auth,
            )

        self.assertEqual(save(first).status_code, 200)
        refused = save(second)
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(list(refused.json()["errors"]), ["answers"])

        attempt_service.submit(attempt)
        closed = save(first)
        self.assertEqual(list(closed.json()["errors"]), ["attempt"])

    def test_the_paper_says_how_many_answers_count(self):
        exam = self.published_exam(questions=3)
        ExamSection.objects.filter(exam=exam).update(required_question_count=2, marks=2)
        attempt = attempt_service.start_attempt(exam, self.student)
        paper = self.client.get(url("attempt_detail", attempt.pk), **self.student_auth).json()["paper"]
        self.assertEqual(paper[0]["answers_required"], 2)

    def test_an_exam_on_a_draft_course_cannot_be_sat(self):
        exam = self.published_exam()
        Course.objects.filter(pk=self.course.pk).update(status=Course.Status.DRAFT)
        self.assertEqual(self.client.post(url("exam_start", exam.pk), **self.student_auth).status_code, 404)

    def test_bad_answers_are_refused(self):
        exam = self.published_exam()
        attempt = attempt_service.start_attempt(exam, self.student)
        q, other = self.questions[0], self.questions[1]
        for answers in (
            [{"question_id": 999999, "option_ids": []}],
            [{"question_id": q.pk, "option_ids": [self.option(other, 0)]}],
            [{"question_id": q.pk, "option_ids": [self.option(q, 0), self.option(q, 1)]}],
        ):
            response = self.client.put(
                url("attempt_answers", attempt.pk), {"answers": answers}, format="json", **self.student_auth
            )
            self.assertEqual(response.status_code, 422, answers)

    def test_answers_after_the_deadline_are_refused_and_the_attempt_closes(self):
        exam = self.published_exam(duration_minutes=30)
        attempt = attempt_service.start_attempt(exam, self.student, now=timezone.now() - timezone.timedelta(hours=1))
        q = self.questions[0]
        response = self.client.put(
            url("attempt_answers", attempt.pk),
            {"answers": [{"question_id": q.pk, "option_ids": [self.option(q, 0)]}]},
            format="json",
            **self.student_auth,
        )
        # Reading closes the expired attempt as it stood, then the write is refused.
        self.assertEqual(response.status_code, 422)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, ExamAttempt.Status.SUBMITTED)
        self.assertEqual(attempt.submitted_at, attempt.deadline)

    def test_another_students_attempt_is_not_found(self):
        exam = self.published_exam()
        attempt = attempt_service.start_attempt(exam, self.other)
        self.assertEqual(self.client.get(url("attempt_detail", attempt.pk), **self.student_auth).status_code, 404)
