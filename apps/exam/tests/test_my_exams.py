"""The student's "My exams" list and the admin CSV export of results."""

import csv
import io

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Course, Enrollment, Section
from apps.exam.models import Exam
from apps.exam.services import attempts as attempt_service
from apps.exam.tests.base import CourseExamTestCase
from apps.identity.models import User

MY_EXAMS_URL = reverse("api:exam:my_exams")


def export_url(exam):
    return reverse("api:exam:admin_exam_attempts_export", args=[exam.pk])


class MyExamsTests(CourseExamTestCase):
    def listed(self):
        response = self.client.get(MY_EXAMS_URL, **self.student_auth)
        self.assertEqual(response.status_code, 200)
        return {row["id"]: row for row in response.json()["data"]}

    def test_each_exam_shows_where_the_student_stands(self):
        now = timezone.now()
        upcoming = self.published_exam(start_time=now + timezone.timedelta(days=1))
        open_exam = self.published_exam()
        sitting = self.published_exam()
        attempt_service.start_attempt(sitting, self.student)
        awaiting = self.published_exam(result_publish_time=now + timezone.timedelta(days=1))
        attempt_service.submit(attempt_service.start_attempt(awaiting, self.student))
        released = self.published_exam(questions=2)
        attempt = attempt_service.start_attempt(released, self.student)
        attempt_service.save_answers(
            attempt, [{"question_id": self.questions[0].pk, "option_ids": [self.option(self.questions[0], 0)]}]
        )
        attempt_service.submit(attempt)
        missed = self.published_exam(end_time=now - timezone.timedelta(hours=1))

        rows = self.listed()
        self.assertEqual(rows[upcoming.pk]["status"], "upcoming")
        self.assertEqual(rows[open_exam.pk]["status"], "open")
        self.assertEqual(rows[sitting.pk]["status"], "in_progress")
        self.assertIsNotNone(rows[sitting.pk]["open_attempt_id"])
        self.assertEqual(rows[awaiting.pk]["status"], "submitted")
        self.assertIsNone(rows[awaiting.pk]["score"])
        self.assertEqual(rows[released.pk]["status"], "result_available")
        self.assertEqual(rows[released.pk]["official_attempt_id"], attempt.pk)
        self.assertEqual(float(rows[released.pk]["score"]), 1.0)
        self.assertEqual(rows[missed.pk]["status"], "missed")
        self.assertEqual(rows[open_exam.pk]["course"]["slug"], self.course.slug)
        self.assertEqual(rows[open_exam.pk]["question_count"], 3)

    def test_only_courses_the_student_can_open_are_listed(self):
        mine = self.published_exam()
        other_course = Course.objects.create(title="Physics", slug="physics", status="published")
        other_section = Section.objects.create(slug=next_slug("section"), course=other_course, title="Ch 1")
        theirs = Exam.objects.get(
            lesson=other_course.contents.create(section=other_section, title="Other test", type="exam")
        )
        theirs.status = Exam.Status.PUBLISHED
        theirs.save()
        draft = self.lesson(title="Draft test").exam

        rows = self.listed()
        self.assertIn(mine.pk, rows)
        self.assertNotIn(theirs.pk, rows)
        self.assertNotIn(draft.pk, rows)

    def test_an_exam_sat_stays_listed_after_access_ends(self):
        sat = self.published_exam()
        attempt_service.submit(attempt_service.start_attempt(sat, self.student))
        unsat = self.published_exam()
        Enrollment.objects.filter(user=self.student).update(valid_till=timezone.now() - timezone.timedelta(days=1))

        rows = self.listed()
        self.assertIn(sat.pk, rows)
        self.assertNotIn(unsat.pk, rows)

    def test_the_list_costs_the_same_queries_however_many_exams(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.client.get(MY_EXAMS_URL, **self.student_auth)
            return len(queries)

        attempt_service.submit(attempt_service.start_attempt(self.published_exam(), self.student))
        few = count()
        for _ in range(4):
            attempt_service.start_attempt(self.published_exam(), self.student)
        self.assertEqual(count(), few)

    def test_a_guest_is_refused(self):
        self.assertEqual(self.client.get(MY_EXAMS_URL).status_code, 401)


class ResultsExportTests(CourseExamTestCase):
    def rows(self, response):
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        return list(csv.reader(io.StringIO(text.lstrip("﻿"))))

    def test_every_attempt_is_a_row(self):
        exam = self.published_exam()
        attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        attempt_service.start_attempt(exam, self.other)

        response = self.client.get(export_url(exam), **self.admin_auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn(f'filename="exam-{exam.pk}-results.csv"', response["Content-Disposition"])

        header, *body = self.rows(response)
        self.assertEqual(header[:3], ["Rank", "Name", "Phone"])
        self.assertEqual(len(body), 2)
        official = next(row for row in body if row[3] == "Official")
        self.assertEqual((official[0], official[1]), ("1", "Student One"))

    def test_a_teacher_of_another_course_cannot_export(self):
        exam = self.published_exam()
        outsider = make_user(role=User.Role.TEACHER)
        self.assertIn(self.client.get(export_url(exam), **bearer(outsider)).status_code, (403, 404))

    def test_a_student_cannot_export(self):
        exam = self.published_exam()
        self.assertEqual(self.client.get(export_url(exam), **self.student_auth).status_code, 403)
