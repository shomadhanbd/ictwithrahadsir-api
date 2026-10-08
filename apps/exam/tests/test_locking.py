"""Once students have sat an exam its paper is fixed; only the key, wording and release times move."""

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import bearer, make_user
from apps.courses.models import CourseTeacher
from apps.exam.models import Exam, ExamAnswer
from apps.exam.services import attempts as attempt_service
from apps.exam.tests.base import CourseExamTestCase, detail, section_questions
from apps.identity.models import User
from apps.question.tests.base import save_question


class AttemptedExamLockTests(CourseExamTestCase):
    def setUp(self):
        super().setUp()
        self.exam = self.published_exam(end_time=timezone.now() + timezone.timedelta(days=1))
        self.section = self.exam.sections.get()
        attempt_service.submit(attempt_service.start_attempt(self.exam, self.student))

    def patch_exam(self, **changes):
        return self.client.patch(
            detail("exam", self.exam.pk), changes, content_type="application/json", **self.admin_auth
        )

    def test_it_cannot_go_back_to_draft(self):
        response = self.patch_exam(status="draft")
        self.assertEqual(response.status_code, 422)
        self.assertIn("Students have taken this exam", str(response.json()["errors"]))
        self.assertEqual(Exam.objects.get(pk=self.exam.pk).status, Exam.Status.PUBLISHED)

    def test_marks_and_timing_are_frozen(self):
        for field, value in (("pass_marks", "1.00"), ("duration_minutes", 90)):
            with self.subTest(field=field):
                self.assertEqual(self.patch_exam(**{field: value}).status_code, 422)

    def test_parts_and_picks_are_frozen(self):
        self.assertEqual(
            self.client.delete(detail("exam_section", self.section.pk), **self.admin_auth).status_code, 422
        )
        kept = list(self.section.section_questions.values_list("block_id", flat=True))
        self.assertEqual(
            self.client.put(
                section_questions(self.section.pk), {"block_ids": kept[1:]}, format="json", **self.admin_auth
            ).status_code,
            422,
        )
        extra, _ = self.mcq()
        response = self.client.put(
            section_questions(self.section.pk), {"block_ids": [*kept, extra.pk]}, format="json", **self.admin_auth
        )
        self.assertEqual(response.status_code, 422)

    def test_release_times_and_wording_stay_editable(self):
        later = timezone.now() + timezone.timedelta(days=3)
        response = self.patch_exam(
            title="Renamed",
            end_time=later.isoformat(),
            result_publish_time=(later + timezone.timedelta(hours=1)).isoformat(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["attempt_count"], 1)

    def test_it_cannot_close_before_now_while_someone_is_sitting_it(self):
        attempt_service.start_attempt(self.exam, self.other)
        response = self.patch_exam(end_time=(timezone.now() - timezone.timedelta(minutes=5)).isoformat())
        self.assertEqual(response.status_code, 422)
        self.assertIn("end_time", response.json()["errors"])

    def test_regrade_still_works(self):
        response = self.client.post(reverse("api:exam:admin_exam_regrade", args=[self.exam.pk]), **self.admin_auth)
        self.assertEqual(response.status_code, 200)


class AnswerKeyLockTests(CourseExamTestCase):
    """A published question keeps its option rows, and only the exam's authors may change it."""

    def setUp(self):
        super().setUp()
        self.exam = self.published_exam(questions=1, negative="0")
        self.question = self.questions[0]
        self.option_ids = list(self.question.options.order_by("position").values_list("pk", flat=True))
        attempt = attempt_service.start_attempt(self.exam, self.student)
        attempt_service.save_answers(attempt, [{"question_id": self.question.pk, "option_ids": [self.option_ids[1]]}])
        self.attempt = attempt_service.submit(attempt)

    def put_options(self, options, auth=None):
        return save_question(self.client, auth or self.admin_auth, {"options": options}, question=self.question)

    def options_with_key(self, correct, *, with_ids=True):
        return [
            {
                **({"id": pk} if with_ids else {}),
                "content": f"option {position}",
                "position": position,
                "is_correct": position == correct,
            }
            for position, pk in enumerate(self.option_ids)
        ]

    def test_options_cannot_be_replaced_under_students_answers(self):
        response = self.put_options(self.options_with_key(1, with_ids=False))
        self.assertEqual(response.status_code, 422)
        self.assertIn("options", response.json()["errors"])
        self.assertEqual(list(self.question.options.order_by("position").values_list("pk", flat=True)), self.option_ids)

    def test_an_option_cannot_be_dropped_or_added(self):
        for label, options in (
            ("dropped", self.options_with_key(0)[:-1]),
            ("added", [*self.options_with_key(0), {"content": "new", "position": 9, "is_correct": False}]),
        ):
            with self.subTest(label):
                self.assertEqual(self.put_options(options).status_code, 422)

    def test_the_key_is_corrected_in_place_and_regraded(self):
        self.assertEqual(self.put_options(self.options_with_key(1)).status_code, 200)
        self.client.post(reverse("api:exam:admin_exam_regrade", args=[self.exam.pk]), **self.admin_auth)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.correct, 1)
        self.assertEqual(ExamAnswer.objects.get(attempt=self.attempt).selected_option_ids, [self.option_ids[1]])

    def test_a_teacher_of_another_course_cannot_touch_the_key(self):
        outsider = bearer(make_user(role=User.Role.TEACHER))
        self.assertEqual(self.put_options(self.options_with_key(1), auth=outsider).status_code, 403)
        self.assertTrue(self.question.options.get(pk=self.option_ids[0]).is_correct)

    def test_a_teacher_of_the_exams_course_can(self):
        teacher = make_user(role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, user=teacher)
        self.assertEqual(self.put_options(self.options_with_key(1), auth=bearer(teacher)).status_code, 200)

    def test_a_teacher_of_another_course_cannot_rewrite_the_block_either(self):
        """The passage, tags and active flag sit on the block, not the question."""
        outsider = bearer(make_user(role=User.Role.TEACHER))
        response = self.client.patch(
            reverse("api:question:admin_question_block_detail", args=[self.question.block_id]),
            {"is_active": False},
            format="json",
            **outsider,
        )
        self.assertEqual(response.status_code, 403)
        self.question.block.refresh_from_db()
        self.assertTrue(self.question.block.is_active)

    def test_a_draft_exams_questions_stay_free_to_rework(self):
        draft = self.lesson(title="Draft test").exam
        section = draft.sections.create(title="MCQ", question_type="mcq", subject=self.subject, marks=1)
        block, question = self.mcq()
        section.section_questions.create(block=block, marks=1)
        response = save_question(
            self.client,
            bearer(make_user(role=User.Role.TEACHER)),
            {"options": [{"content": "a", "position": 0, "is_correct": True}, {"content": "b", "position": 1}]},
            question=question,
        )
        self.assertEqual(response.status_code, 200, response.content)
