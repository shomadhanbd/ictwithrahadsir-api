"""Creating exams, their configuration rules, ownership and the list."""

from types import SimpleNamespace

from django.db import IntegrityError, transaction

from apps.academic.models import Batch
from apps.core.testing import bearer, make_user
from apps.exam.api.private.permissions import IsExamAuthor
from apps.exam.models import Exam, ExamSectionQuestion
from apps.exam.selectors import admin_exams
from apps.exam.tests.base import (
    EXAMS_URL,
    SECTIONS_URL,
    ExamTestCase,
    detail,
    section_questions,
)
from apps.identity.models import User


class ExamAuthoringTests(ExamTestCase):
    def test_exams_are_not_created_here(self):
        """Exams are created as lessons inside a course."""
        for scope in ("standalone", "batch", "course"):
            with self.subTest(scope=scope):
                response = self.client.post(
                    EXAMS_URL,
                    {"title": "New", "total_marks": "50.00", "scope": scope},
                    content_type="application/json",
                    **self.auth,
                )
                self.assertEqual(response.status_code, 422)
                self.assertIn("scope", response.json()["errors"])
        self.assertFalse(Exam.objects.exists())

    def test_the_list_is_enveloped_and_the_detail_is_not(self):
        exam = self.exam()

        listed = self.client.get(EXAMS_URL, **self.auth).json()
        self.assertEqual(listed["meta"]["total"], 1)
        self.assertEqual([row["id"] for row in listed["data"]], [exam.pk])

        self.assertEqual(self.client.get(detail("exam", exam.pk), **self.auth).json()["id"], exam.pk)


class ExamConfigurationRuleTests(ExamTestCase):
    def patch(self, **changes):
        exam = self.exam()
        return self.client.patch(detail("exam", exam.pk), changes, content_type="application/json", **self.auth)

    def assert_refused(self, field, **changes):
        response = self.patch(**changes)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn(field, response.json()["errors"])

    def test_pass_marks_must_be_positive(self):
        self.assert_refused("pass_marks", pass_marks="0.00")

    def test_an_exam_cannot_end_before_it_starts(self):
        self.assert_refused("end_time", start_time="2026-10-01T10:00:00Z", end_time="2026-10-01T09:00:00Z")

    def test_results_cannot_publish_before_the_exam_closes(self):
        self.assert_refused(
            "result_publish_time",
            start_time="2026-10-01T10:00:00Z",
            end_time="2026-10-01T12:00:00Z",
            result_publish_time="2026-10-01T11:00:00Z",
        )

    def test_an_exam_allows_at_least_one_attempt(self):
        self.assert_refused("max_attempts", max_attempts=0)

    def test_a_batch_exam_needs_a_batch(self):
        self.assert_refused("batch_id", scope="batch")

    def test_an_exam_cannot_become_a_course_exam_here(self):
        self.assert_refused("scope", scope="course")

    def test_a_standalone_exam_carries_no_scope_column(self):
        batch = Batch.objects.create(name="SSC-2027", class_level=self.ssc, slug="ssc-2027")

        self.assert_refused("scope", scope="standalone", batch_id=batch.pk)

    def test_the_database_refuses_a_zero_attempt_exam(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exam.objects.create(title="Raw", max_attempts=0)


class ExamOwnershipTests(ExamTestCase):
    def setUp(self):
        super().setUp()
        self.mine = self.exam(title="Mine", created_by=self.teacher)
        self.theirs = self.exam(title="Theirs", created_by=self.other_teacher)

    def test_a_teacher_lists_only_their_own_exams(self):
        body = self.client.get(EXAMS_URL, **self.teacher_auth).json()

        self.assertEqual([row["id"] for row in body["data"]], [self.mine.pk])

    def test_a_teacher_sees_only_their_own_exams_sections(self):
        mine = self.section(exam=self.mine)
        theirs = self.section(exam=self.theirs)

        body = self.client.get(SECTIONS_URL, **self.teacher_auth).json()
        self.assertEqual([row["id"] for row in body["data"]], [mine.pk])
        response = self.client.get(detail("exam_section", theirs.pk), **self.teacher_auth)
        self.assertIn(response.status_code, (403, 404))

    def test_an_admin_lists_every_exam(self):
        body = self.client.get(EXAMS_URL, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 2)

    def test_a_teacher_cannot_open_another_teachers_exam_by_id(self):
        response = self.client.get(detail("exam", self.theirs.pk), **self.teacher_auth)

        self.assertIn(response.status_code, (403, 404))

    def test_a_teacher_cannot_edit_another_teachers_exam(self):
        response = self.client.patch(
            detail("exam", self.theirs.pk),
            {"title": "Hijacked"},
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertIn(response.status_code, (403, 404))
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, "Theirs")

    def test_a_teacher_cannot_hang_a_section_off_another_teachers_exam(self):
        """DRF runs no object permission on a POST to a child collection."""
        response = self.client.post(
            SECTIONS_URL,
            {
                "exam_id": self.theirs.pk,
                "title": "Sneaked in",
                "question_type": "mcq",
                "subject_id": self.ict.pk,
                "marks": "30.00",
            },
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.theirs.sections.count(), 0)

    def test_a_teacher_cannot_bulk_pick_into_another_teachers_section(self):
        """A plain `APIView` runs no object permission either."""
        section = self.section(exam=self.theirs)

        response = self.client.put(
            section_questions(section.pk),
            {"block_ids": [self.mcq_block().pk]},
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ExamSectionQuestion.objects.count(), 0)

    def test_the_object_guard_refuses_on_its_own(self):
        """Pins the object guard itself; via the API the queryset filter already hides the exam."""
        view = SimpleNamespace(exam_for=lambda obj: obj)
        guard = IsExamAuthor()

        mine = SimpleNamespace(user=self.teacher)
        self.assertTrue(guard.has_object_permission(mine, view, self.mine))
        self.assertFalse(guard.has_object_permission(mine, view, self.theirs))

        # An admin passes everything, including an orphaned exam.
        as_admin = SimpleNamespace(user=self.admin)
        self.assertTrue(guard.has_object_permission(as_admin, view, self.theirs))

        # A NULL author matches nobody rather than everybody.
        self.theirs.created_by = None
        self.assertFalse(guard.has_object_permission(mine, view, self.theirs))

    def test_an_orphaned_exam_falls_to_admins_not_to_everyone(self):
        """A NULL author matches no teacher's filter."""
        Exam.objects.filter(pk=self.mine.pk).update(created_by=None)

        self.assertEqual(self.client.get(EXAMS_URL, **self.teacher_auth).json()["meta"]["total"], 0)
        self.assertEqual(self.client.get(EXAMS_URL, **self.auth).json()["meta"]["total"], 2)

    def test_deleting_a_teacher_does_not_take_their_exams_with_them(self):
        self.other_teacher.delete()

        self.assertTrue(Exam.objects.filter(pk=self.theirs.pk).exists())


class PermissionTests(ExamTestCase):
    """Exam payloads reach the answer key, so they are for teaching staff only."""

    def setUp(self):
        super().setUp()
        self.row = self.section()

    def _urls(self):
        return [
            EXAMS_URL,
            SECTIONS_URL,
            detail("exam", self.row.exam_id),
            detail("exam_section", self.row.pk),
            section_questions(self.row.pk),
        ]

    def test_a_student_is_refused(self):
        auth = bearer(make_user())
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_a_moderator_is_refused(self):
        """The notices desk has no business in the question bank."""
        auth = bearer(make_user(role=User.Role.MODERATOR))
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_an_anonymous_caller_is_refused(self):
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 401, url)


class ExamListOrderingTests(ExamTestCase):
    """The aggregates add a GROUP BY, which drops `Meta.ordering` unless the queryset orders."""

    def test_the_queryset_is_ordered(self):
        self.assertTrue(admin_exams().ordered)
        self.assertIn("ORDER BY", str(admin_exams().query))

    def test_the_page_is_newest_first(self):
        for title in ("First", "Second", "Third"):
            self.exam(title=title)

        response = self.client.get(EXAMS_URL, **self.auth)

        titles = [row["title"] for row in response.json()["data"]]
        self.assertEqual(titles, sorted(titles, key=lambda t: ["Third", "Second", "First"].index(t)))
        self.assertEqual(titles[0], "Third")


class ExamListQueryBudgetTests(ExamTestCase):
    def build(self, exams):
        for index in range(exams):
            exam = self.exam(title=f"Paper {index}")
            for title in ("MCQ", "সৃজনশীল"):
                section = self.section(exam=exam, title=title)
                for _ in range(3):
                    ExamSectionQuestion.objects.create(section=section, block=self.mcq_block())

    def test_the_page_costs_a_fixed_number_of_queries(self):
        self.build(6)

        # token, role groups, count, exams, section-type prefetch
        with self.assertNumQueries(5):
            self.client.get(EXAMS_URL, **self.auth)

    def test_the_cost_does_not_move_with_the_fixture(self):
        self.build(12)

        with self.assertNumQueries(5):
            self.client.get(EXAMS_URL, **self.auth)

    def test_the_detail_tree_costs_a_fixed_number_of_queries(self):
        """Several sections, so a per-section query would show."""
        self.build(1)
        exam = Exam.objects.first()
        for title in ("Third", "Fourth"):
            self.section(exam=exam, title=title, marks=1)

        # token, role groups, exam, sections, picks
        with self.assertNumQueries(5):
            self.client.get(detail("exam", exam.pk), **self.auth)
