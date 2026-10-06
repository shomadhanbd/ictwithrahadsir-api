"""Who may delete curriculum, grant enrolments, and reach a lesson; and what a course card counts."""

from django.urls import reverse

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.courses.models import Content, Course, CourseMaterial, CourseTeacher, Enrollment, Routine, Section
from apps.identity.models import User

ENROLMENT_URL = reverse("api:courses:admin_enrollment")


class CurriculumRulesTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title="ICT", slug="ict-rules", status="published")
        self.section = Section.objects.create(course=self.course, title="Ch 1", slug="ict-rules-ch1")
        self.lesson = Content.objects.create(
            course=self.course, section=self.section, title="L1", slug="ict-rules-l1", type="video", paid=False
        )
        self.teacher = make_user(role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, user=self.teacher)
        self.teacher_auth = bearer(self.teacher)
        self.admin_auth = bearer(make_user(role=User.Role.ADMIN))
        self.student = make_user()

    def test_a_teacher_edits_but_cannot_delete_lessons_or_sections(self):
        lesson_url = f"/api/private/contents/{self.lesson.slug}/"
        section_url = f"/api/private/sections/{self.section.slug}/"
        self.assertEqual(
            self.client.patch(lesson_url, {"title": "L1b"}, format="json", **self.teacher_auth).status_code, 200
        )
        self.assertEqual(self.client.delete(lesson_url, **self.teacher_auth).status_code, 403)
        self.assertEqual(self.client.delete(section_url, **self.teacher_auth).status_code, 403)
        self.assertTrue(Content.objects.filter(pk=self.lesson.pk).exists())
        self.assertEqual(self.client.delete(lesson_url, **self.admin_auth).status_code, 204)

    def test_a_teacher_cannot_delete_their_course_or_its_routines_and_materials(self):
        routine = Routine.objects.create(course=self.course, title="Week 1")
        material = CourseMaterial.objects.create(course=self.course, title="Sheet")
        for url in (
            f"/api/private/courses/{self.course.slug}/",
            f"/api/private/routines/{routine.pk}/",
            f"/api/private/course-materials/{material.pk}/",
        ):
            with self.subTest(url=url):
                response = self.client.delete(url, **self.teacher_auth)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["message"], "Only an admin may delete part of a course.")
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())

    def test_only_an_admin_grants_or_changes_enrolments(self):
        body = {"user_id": self.student.pk, "course_id": self.course.pk}
        for method in ("post", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(ENROLMENT_URL, body, format="json", **self.teacher_auth)
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Enrollment.objects.exists())
        self.assertEqual(self.client.post(ENROLMENT_URL, body, format="json", **self.admin_auth).status_code, 201)

    def lesson_status(self, auth=None):
        return self.client.get(
            reverse("api:courses:content_detail", args=[self.lesson.slug]), **(auth or {})
        ).status_code

    def test_a_free_lesson_of_a_draft_course_is_not_reachable(self):
        self.assertEqual(self.lesson_status(), 200)
        Course.objects.filter(pk=self.course.pk).update(status=Course.Status.DRAFT)
        self.assertEqual(self.lesson_status(), 404)
        self.assertEqual(self.lesson_status(self.teacher_auth), 200)  # its own teacher previews it

    def test_a_lesson_in_a_switched_off_section_is_not_reachable(self):
        Section.objects.filter(pk=self.section.pk).update(active=False)
        self.assertEqual(self.lesson_status(), 404)

    def test_a_lesson_under_a_switched_off_parent_section_is_not_reachable(self):
        parent = Section.objects.create(course=self.course, title="Part", slug="ict-rules-part", active=False)
        Section.objects.filter(pk=self.section.pk).update(section=parent)
        self.assertEqual(self.lesson_status(), 404)

    def test_course_cards_count_only_lessons_students_can_see(self):
        Content.objects.create(
            course=self.course, section=self.section, title="Off", slug="ict-rules-off", type="video", active=False
        )
        hidden = Section.objects.create(course=self.course, title="Hidden", slug="ict-rules-hidden", active=False)
        Content.objects.create(course=self.course, section=hidden, title="H", slug="ict-rules-h", type="video")
        card = next(
            c for c in self.client.get(reverse("api:courses:course_list")).json()["data"] if c["slug"] == "ict-rules"
        )
        self.assertEqual(card["lesson_counts"]["video"], 1)


class VisibleLessonCountTests(APITestCase):
    """Cards, progress and the export count the lessons a student can see, so 100% is reachable."""

    def setUp(self):
        self.course = Course.objects.create(title="ICT", slug="ict-visible", status="published")
        shown = Section.objects.create(course=self.course, title="Shown", slug="ict-visible-shown")
        hidden_parent = Section.objects.create(course=self.course, title="Off", slug="ict-visible-off", active=False)
        under_hidden = Section.objects.create(
            course=self.course, section=hidden_parent, title="Sub", slug="ict-visible-sub"
        )
        self.lesson = Content.objects.create(
            course=self.course, section=shown, title="L", slug="ict-visible-l", type="video", paid=False
        )
        Content.objects.create(course=self.course, section=under_hidden, title="H", slug="ict-visible-h", type="video")
        self.student = make_user()
        Enrollment.objects.create(course=self.course, user=self.student)

    def test_a_student_who_finished_every_visible_lesson_is_at_100(self):
        auth = bearer(self.student)
        url = reverse("api:courses:course_progress", args=[self.course.slug])
        self.client.post(url, {"content_id": self.lesson.pk}, format="json", **auth)
        progress = self.client.get(url, **auth).json()["data"]
        self.assertEqual((progress["completed"], progress["total"], progress["percent"]), (1, 1, 100))

    def test_the_card_leaves_out_lessons_under_a_hidden_parent(self):
        card = next(
            c for c in self.client.get(reverse("api:courses:course_list")).json()["data"] if c["slug"] == "ict-visible"
        )
        self.assertEqual(card["lesson_counts"]["video"], 1)


class TeacherPreviewTests(APITestCase):
    def test_a_teacher_previews_a_paid_lesson_of_their_draft(self):
        course = Course.objects.create(title="Draft", slug="draft-preview", status="draft")
        section = Section.objects.create(course=course, title="Ch", slug="draft-preview-ch")
        lesson = Content.objects.create(course=course, section=section, title="Paid", slug="draft-paid", type="video")
        teacher = make_user(role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=course, user=teacher)
        url = reverse("api:courses:content_detail", args=[lesson.slug])
        self.assertEqual(self.client.get(url, **bearer(teacher)).status_code, 200)
        self.assertEqual(self.client.get(url, **bearer(make_user())).status_code, 404)
