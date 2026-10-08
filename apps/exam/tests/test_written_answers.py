"""Course exams with creative questions: uploaded answer sheets, teacher marking, and results that wait for it."""

import shutil
import tempfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from PIL import Image

from apps.core.testing import bearer, make_user
from apps.exam.models import Exam, ExamAttempt, ExamSection, ExamSectionQuestion
from apps.exam.tests.base import CourseExamTestCase, section_questions, url
from apps.question.models import Question, QuestionBlock, QuestionSet

PART_MARKS = {"ক": 1, "খ": 2, "গ": 3, "ঘ": 4}


def photo(name="answer.jpg"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class WrittenAnswerTests(CourseExamTestCase):
    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media, API_BASE_URL="https://api.example.test")
        override.enable()
        self.addCleanup(override.disable)

    def cq(self, marks=PART_MARKS):
        block = QuestionBlock.objects.create(subject=self.subject, kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="উদ্দীপক")
        for order, (label, value) in enumerate(marks.items()):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.CQ,
                label=label,
                order_in_set=order,
                prompt_content=f"part {label}",
                model_answer=f"model {label}",
                marks=value,
            )
        block.refresh_from_db()
        return block

    def mixed_exam(self, pass_marks=None):
        """Two one-mark MCQs and one 10-mark creative question (ক1 খ2 গ3 ঘ4)."""
        exam = self.lesson().exam
        mcq = ExamSection.objects.create(
            exam=exam, title="MCQ", question_type="mcq", subject=self.subject, marks=2, marks_per_question=1
        )
        self.mcqs = []
        for order in range(2):
            block, question = self.mcq(correct=0)
            ExamSectionQuestion.objects.create(section=mcq, block=block, marks=1, order=order)
            self.mcqs.append(question)
        written = ExamSection.objects.create(
            exam=exam, title="সৃজনশীল", question_type="cq", subject=self.subject, marks=10, marks_per_question=10
        )
        self.cq_block = self.cq()
        self.placement = ExamSectionQuestion.objects.create(section=written, block=self.cq_block, marks=10)
        self.parts = list(Question.objects.filter(question_set__block=self.cq_block).order_by("order_in_set"))
        exam.pass_marks = pass_marks
        exam.status = Exam.Status.PUBLISHED
        exam.save()
        return exam

    def start(self, exam, auth=None):
        response = self.client.post(url("exam_start", exam.pk), **(auth or self.student_auth))
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def upload(self, attempt_id, placement=None, file=None, auth=None):
        return self.client.post(
            url("attempt_sheet_files", attempt_id, (placement or self.placement).pk),
            {"file": file or photo()},
            format="multipart",
            **(auth or self.student_auth),
        )

    def answer_mcqs(self, attempt_id):
        answers = [{"question_id": q.pk, "option_ids": [self.option(q, 0)]} for q in self.mcqs]
        response = self.client.put(
            url("attempt_answers", attempt_id), {"answers": answers}, format="json", **self.student_auth
        )
        self.assertEqual(response.status_code, 200, response.content)

    def submit(self, attempt_id):
        self.assertEqual(self.client.post(url("attempt_submit", attempt_id), **self.student_auth).status_code, 200)

    def mark(self, exam, attempt_id, marks):
        return self.client.put(
            url("admin_exam_attempt_marks", exam.pk, attempt_id),
            {"marks": [{"question_id": q.pk, "marks": m} for q, m in marks]},
            format="json",
            **self.admin_auth,
        )

    def result(self, attempt_id):
        return self.client.get(url("attempt_result", attempt_id), **self.student_auth).json()

    def test_the_total_is_what_the_paper_adds_up_to(self):
        exam = self.mixed_exam()
        exam.refresh_from_db()
        self.assertEqual(exam.total_marks, Decimal("12"))

    def test_a_creative_question_must_add_up_to_its_section_rate(self):
        exam = self.lesson().exam
        section = ExamSection.objects.create(
            exam=exam, title="CQ", question_type="cq", subject=self.subject, marks=10, marks_per_question=10
        )
        short = self.cq({"ক": 1, "খ": 2, "গ": 3, "ঘ": 2})
        response = self.client.put(
            section_questions(section.pk), {"block_ids": [short.pk]}, format="json", **self.admin_auth
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("add up to 8", str(response.json()["errors"]))

    def test_the_paper_says_which_parts_take_an_upload(self):
        attempt_id = self.start(self.mixed_exam())
        body = self.client.get(url("attempt_detail", attempt_id), **self.student_auth).json()
        written = next(section for section in body["paper"] if section["question_type"] == "cq")
        item = written["items"][0]
        self.assertEqual(item["section_question_id"], self.placement.pk)
        self.assertEqual([q["marks"] for q in item["questions"]], [1, 2, 3, 4])
        self.assertEqual(body["sheets"], [])

    def test_a_student_uploads_and_removes_answer_photos(self):
        attempt_id = self.start(self.mixed_exam())
        response = self.upload(attempt_id)
        self.assertEqual(response.status_code, 201, response.content)
        link = response.json()["files"][0]["link"]
        # The public API origin, not the host the request came in on (the website's server calls an internal one).
        self.assertTrue(link.startswith("https://api.example.test/media/uploads/exam-answers/"))
        self.assertTrue(link.endswith(".jpg"))
        self.upload(attempt_id)
        body = self.client.get(url("attempt_detail", attempt_id), **self.student_auth).json()
        self.assertEqual(len(body["sheets"][0]["files"]), 2)

        removed = self.client.delete(
            url("attempt_sheet_files", attempt_id, self.placement.pk),
            {"link": link},
            format="json",
            **self.student_auth,
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        self.assertEqual(len(removed.json()["files"]), 1)

    def test_uploads_are_refused_where_they_do_not_belong(self):
        exam = self.mixed_exam()
        attempt_id = self.start(exam)
        mcq_placement = ExamSectionQuestion.objects.get(block__standalone_question=self.mcqs[0])
        self.assertEqual(self.upload(attempt_id, placement=mcq_placement).status_code, 422)
        fake = SimpleUploadedFile("answer.jpg", b"not a picture", content_type="image/jpeg")
        self.assertEqual(self.upload(attempt_id, file=fake).status_code, 422)
        self.assertEqual(self.upload(attempt_id, auth=bearer(self.other)).status_code, 404)

        self.submit(attempt_id)
        response = self.upload(attempt_id)
        self.assertEqual(response.status_code, 422)
        self.assertIn("attempt", response.json()["errors"])

    def test_a_refused_photo_is_explained_in_bangla(self):
        attempt_id = self.start(self.mixed_exam())
        fake = SimpleUploadedFile("answer.jpg", b"not a picture", content_type="image/jpeg")
        unreadable = self.upload(attempt_id, file=fake).json()["errors"]["file"][0]
        self.assertIn("ফাইলটি পড়া যাচ্ছে না", unreadable)
        with patch("apps.uploads.validators.MAX_IMAGE_BYTES", 10):
            too_large = self.upload(attempt_id).json()["errors"]["file"][0]
        self.assertEqual(too_large, "ফাইলটি সর্বোচ্চ ০ MB হতে পারে।")

    def test_an_uploaded_answer_waits_for_marking(self):
        exam = self.mixed_exam(pass_marks=5)
        attempt_id = self.start(exam)
        self.answer_mcqs(attempt_id)
        self.upload(attempt_id)
        self.submit(attempt_id)

        attempt = ExamAttempt.objects.get(pk=attempt_id)
        self.assertTrue(attempt.awaiting_marking)
        body = self.result(attempt_id)
        self.assertTrue(body["awaiting_marking"])
        self.assertIsNone(body["score"])
        self.assertIsNone(body["passed"])
        self.assertEqual(Decimal(str(body["mcq_score"])), Decimal("2"))
        self.assertEqual([part["marks"] for part in body["written"][0]["parts"]], [None] * 4)
        self.assertEqual(body["written"][0]["parts"][0]["model_answer"], "")

        ranking = self.client.get(url("exam_ranking", exam.pk), **self.student_auth).json()
        self.assertEqual((ranking["total"], ranking["pending"]), (0, 1))

        summary = self.client.get(url("admin_exam_attempts", exam.pk), **self.admin_auth).json()["summary"]
        self.assertEqual((summary["submitted"], summary["to_mark"]), (1, 1))
        self.assertIsNone(summary["average"])

    def test_a_question_left_unanswered_is_not_waited_for(self):
        attempt_id = self.start(self.mixed_exam())
        self.answer_mcqs(attempt_id)
        self.submit(attempt_id)
        attempt = ExamAttempt.objects.get(pk=attempt_id)
        self.assertFalse(attempt.awaiting_marking)
        self.assertEqual(attempt.score, Decimal("2"))

    def test_marking_every_part_completes_the_result(self):
        exam = self.mixed_exam(pass_marks=5)
        attempt_id = self.start(exam)
        self.answer_mcqs(attempt_id)
        self.upload(attempt_id)
        self.submit(attempt_id)

        partial = self.mark(exam, attempt_id, [(self.parts[0], 1), (self.parts[1], 2)])
        self.assertEqual(partial.status_code, 200, partial.content)
        self.assertTrue(partial.json()["awaiting_marking"])

        done = self.mark(exam, attempt_id, [(self.parts[2], "2.5"), (self.parts[3], 3)])
        self.assertEqual(done.status_code, 200, done.content)
        self.assertFalse(done.json()["awaiting_marking"])

        body = self.result(attempt_id)
        self.assertEqual(Decimal(str(body["score"])), Decimal("10.5"))
        self.assertEqual(Decimal(str(body["cq_score"])), Decimal("8.5"))
        self.assertTrue(body["passed"])
        self.assertEqual(body["written"][0]["parts"][3]["model_answer"], "model ঘ")
        ranking = self.client.get(url("exam_ranking", exam.pk), **self.student_auth).json()
        self.assertEqual((ranking["total"], ranking["pending"]), (1, 0))

    def test_marks_stay_within_the_part_and_on_written_parts(self):
        exam = self.mixed_exam()
        attempt_id = self.start(exam)
        self.upload(attempt_id)
        self.assertEqual(self.mark(exam, attempt_id, [(self.parts[0], 1)]).status_code, 422)  # not submitted yet
        self.submit(attempt_id)

        too_many = self.mark(exam, attempt_id, [(self.parts[0], 2)])
        self.assertEqual(too_many.status_code, 422)
        self.assertIn("out of 1", str(too_many.json()["errors"]))
        self.assertEqual(self.mark(exam, attempt_id, [(self.mcqs[0], 1)]).status_code, 422)

    def test_only_staff_who_manage_the_exam_mark_it(self):
        exam = self.mixed_exam()
        attempt_id = self.start(exam)
        self.upload(attempt_id)
        self.submit(attempt_id)
        response = self.client.put(
            url("admin_exam_attempt_marks", exam.pk, attempt_id),
            {"marks": [{"question_id": self.parts[0].pk, "marks": 1}]},
            format="json",
            **bearer(make_user()),
        )
        self.assertEqual(response.status_code, 403)
