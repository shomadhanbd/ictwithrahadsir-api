"""A course lesson that is an exam."""

from django.urls import reverse

from apps.core.testing import bearer, make_user
from apps.courses.models import Content, CourseTeacher
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.services import attempts as attempt_service
from apps.exam.tests.base import (
    LESSONS_URL,
    CourseExamTestCase,
)
from apps.identity.models import User


class LessonExamLinkTests(CourseExamTestCase):
    def test_an_exam_lesson_creates_a_draft_course_exam(self):
        response = self.client.post(
            LESSONS_URL,
            {
                "course_id": self.course.pk,
                "section_id": self.chapter.pk,
                "title": "Weekly test",
                "slug": "weekly-test",
                "type": "exam",
            },
            format="json",
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        exam = Exam.objects.get(lesson_id=response.json()["id"])
        self.assertEqual((exam.scope, exam.status, exam.title), ("course", "draft", "Weekly test"))
        self.assertEqual(response.json()["exam"]["id"], exam.pk)

    def test_other_lessons_get_no_exam(self):
        Content.objects.create(course=self.course, section=self.chapter, type="video", title="Class 1")
        self.assertFalse(Exam.objects.exists())

    def test_an_exam_lesson_cannot_change_type_either_way(self):
        exam_lesson = self.lesson()
        video = Content.objects.create(course=self.course, section=self.chapter, type="video", title="Class 1")
        for lesson, new_type in ((exam_lesson, "video"), (video, "exam")):
            response = self.client.patch(
                reverse("api:courses:admin_content_detail", args=[lesson.pk]),
                {"type": new_type},
                format="json",
                **self.admin_auth,
            )
            self.assertEqual(response.status_code, 422, new_type)

    def test_a_course_exam_takes_cq_parts_too(self):
        exam = self.lesson().exam
        response = self.client.post(
            reverse("api:exam:admin_exam_section_list"),
            {"exam_id": exam.pk, "title": "CQ", "question_type": "cq", "subject_id": self.subject.pk, "marks": 10},
            format="json",
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_course_exam_cannot_be_made_through_the_exams_endpoint(self):
        response = self.client.post(
            reverse("api:exam:admin_exam_list"), {"title": "X", "scope": "course"}, format="json", **self.admin_auth
        )
        self.assertEqual(response.status_code, 422)

    def test_a_course_exam_publishes_without_a_start_time(self):
        exam = self.lesson().exam
        exam.total_marks = 1
        exam.save()
        section = ExamSection.objects.create(
            exam=exam, title="MCQ", question_type="mcq", subject=self.subject, marks=1, marks_per_question=1
        )
        ExamSectionQuestion.objects.create(section=section, block=self.mcq()[0], marks=1)
        response = self.client.patch(
            reverse("api:exam:admin_exam_detail", args=[exam.pk]),
            {"status": "published"},
            format="json",
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_course_exam_is_deleted_with_its_lesson_not_alone(self):
        exam = self.lesson().exam
        response = self.client.delete(reverse("api:exam:admin_exam_detail", args=[exam.pk]), **self.admin_auth)
        self.assertEqual(response.status_code, 422)
        self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())

    def test_deleting_a_lesson_deletes_its_untaken_exam(self):
        lesson = self.lesson()
        lesson.delete()
        self.assertFalse(Exam.objects.exists())

    def test_a_taken_exam_keeps_its_lesson(self):
        exam = self.published_exam()
        attempt_service.start_attempt(exam, self.student)
        response = self.client.delete(
            reverse("api:courses:admin_content_detail", args=[exam.lesson.pk]), **self.admin_auth
        )
        self.assertEqual(response.status_code, 409)

    def test_the_course_teacher_manages_the_course_exam(self):
        teacher = make_user(role=User.Role.TEACHER)
        exam = self.lesson().exam
        url_ = reverse("api:exam:admin_exam_detail", args=[exam.pk])
        teacher_auth = bearer(teacher)
        self.assertEqual(self.client.get(url_, **teacher_auth).status_code, 404)
        CourseTeacher.objects.create(course=self.course, user=teacher)
        response = self.client.get(url_, **teacher_auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lesson"]["course_id"], self.course.pk)

    def test_the_lesson_payload_shows_the_exam_once_published(self):
        lesson_url = reverse("api:courses:content_detail", args=[self.lesson(paid=False).pk])
        self.assertIsNone(self.client.get(lesson_url, **self.student_auth).json()["exam"])
        exam = Exam.objects.get()
        exam.status = Exam.Status.PUBLISHED
        exam.save()
        self.assertEqual(self.client.get(lesson_url, **self.student_auth).json()["exam"]["id"], exam.pk)
