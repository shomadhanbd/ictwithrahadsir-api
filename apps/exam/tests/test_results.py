"""Results, ranking and the admin view of submissions."""

from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import make_user
from apps.courses.models import Enrollment
from apps.exam import selectors
from apps.exam.models import ExamAttempt
from apps.exam.services import attempts as attempt_service
from apps.exam.services import grading
from apps.exam.tests.base import (
    CourseExamTestCase,
    url,
)


class ResultsTests(CourseExamTestCase):
    def test_the_result_waits_for_its_release_time(self):
        exam = self.published_exam(result_publish_time=timezone.now() + timezone.timedelta(days=1))
        attempt = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        self.assertEqual(self.client.get(url("attempt_result", attempt.pk), **self.student_auth).status_code, 403)

    def test_with_no_result_time_the_result_waits_for_the_exam_to_close(self):
        exam = self.published_exam(end_time=timezone.now() + timezone.timedelta(hours=2))
        attempt = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        self.assertEqual(self.client.get(url("attempt_result", attempt.pk), **self.student_auth).status_code, 403)
        self.assertEqual(self.client.get(url("exam_ranking", exam.slug), **self.student_auth).status_code, 403)

        type(exam).objects.filter(pk=exam.pk).update(end_time=timezone.now() - timezone.timedelta(minutes=1))
        self.assertEqual(self.client.get(url("attempt_result", attempt.pk), **self.student_auth).status_code, 200)
        self.assertEqual(self.client.get(url("exam_ranking", exam.slug), **self.student_auth).status_code, 200)

    def test_with_no_times_set_the_result_is_out_on_submit(self):
        exam = self.published_exam()
        attempt = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        self.assertEqual(self.client.get(url("attempt_result", attempt.pk), **self.student_auth).status_code, 200)

    def test_the_result_shows_the_key_and_explanations(self):
        exam = self.published_exam(questions=1)
        attempt = attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        body = self.client.get(url("attempt_result", attempt.pk), **self.student_auth).json()
        question = body["questions"][0]
        self.assertEqual(question["correct_option_ids"], [self.option(self.questions[0], 0)])
        self.assertEqual(question["explanation"], "Because.")
        self.assertEqual(body["exam"]["lesson_slug"], exam.lesson.slug)
        self.assertEqual(body["exam"]["course_slug"], exam.lesson.course.slug)

    def test_ranking_orders_official_results_and_finds_me(self):
        exam = self.published_exam(questions=2, negative="0")
        for user, right in ((self.student, 1), (self.other, 2)):
            attempt = attempt_service.start_attempt(exam, user)
            attempt_service.save_answers(
                attempt,
                [{"question_id": q.pk, "option_ids": [self.option(q, 0)]} for q in self.questions[:right]],
            )
            attempt_service.submit(attempt)
        body = self.client.get(url("exam_ranking", exam.slug), **self.student_auth).json()
        self.assertEqual([row["name"] for row in body["top"]], ["Student Two", "Student One"])
        self.assertEqual(body["me"]["rank"], 2)

    def test_admin_sees_every_submission(self):
        exam = self.published_exam()
        attempt_service.submit(attempt_service.start_attempt(exam, self.student))
        attempt_service.start_attempt(exam, self.other)
        body = self.client.get(reverse("api:exam:admin_exam_attempts", args=[exam.pk]), **self.admin_auth).json()
        self.assertEqual(body["summary"]["submitted"], 1)
        self.assertEqual(body["summary"]["in_progress"], 1)
        self.assertEqual(len(body["data"]), 2)

    def test_admin_opens_one_attempt_answer_by_answer(self):
        exam = self.published_exam(questions=2)
        attempt = attempt_service.start_attempt(exam, self.student)
        right = self.option(self.questions[0], 0)
        attempt_service.save_answers(attempt, [{"question_id": self.questions[0].pk, "option_ids": [right]}])
        attempt_service.submit(attempt)

        detail = reverse("api:exam:admin_exam_attempt_detail", args=[exam.pk, attempt.pk])
        body = self.client.get(detail, **self.admin_auth).json()
        self.assertEqual(body["user"]["id"], self.student.pk)
        answered, skipped = body["questions"]
        self.assertEqual((answered["selected_option_ids"], answered["is_correct"]), ([right], True))
        self.assertEqual((skipped["selected_option_ids"], skipped["is_correct"]), ([], None))

    def test_an_attempt_is_only_found_under_its_own_exam(self):
        attempt = attempt_service.start_attempt(self.published_exam(), self.student)
        other_exam = self.lesson(title="Other").exam
        detail = reverse("api:exam:admin_exam_attempt_detail", args=[other_exam.pk, attempt.pk])
        self.assertEqual(self.client.get(detail, **self.admin_auth).status_code, 404)
        self.assertEqual(self.client.get(detail, **self.student_auth).status_code, 403)


class ResultTimeRuleTests(CourseExamTestCase):
    def patch(self, exam, **changes):
        return self.client.patch(
            url("admin_exam_detail", exam.pk), changes, content_type="application/json", **self.admin_auth
        )

    def test_a_result_time_needs_an_end_time(self):
        """Without one, students could sit the paper after its answers are out."""
        exam = self.published_exam()
        later = timezone.now() + timezone.timedelta(days=1)

        response = self.patch(exam, result_publish_time=later.isoformat())
        self.assertEqual(response.status_code, 422)
        self.assertIn("result_publish_time", response.json()["errors"])

        response = self.patch(
            exam,
            end_time=later.isoformat(),
            result_publish_time=(later + timezone.timedelta(hours=1)).isoformat(),
        )
        self.assertEqual(response.status_code, 200, response.content)


class LegacyResultTimeTests(CourseExamTestCase):
    def test_an_exam_saved_before_the_rule_can_still_be_renamed(self):
        exam = self.published_exam()
        type(exam).objects.filter(pk=exam.pk).update(result_publish_time=timezone.now() + timezone.timedelta(days=1))
        response = self.client.patch(
            url("admin_exam_detail", exam.pk), {"title": "Renamed"}, content_type="application/json", **self.admin_auth
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_it_cannot_be_published_with_a_result_time_and_no_end(self):
        """A status-only edit touches neither time, but publishing is when the rule matters most."""
        exam = self.published_exam()
        type(exam).objects.filter(pk=exam.pk).update(
            status="draft", result_publish_time=timezone.now() + timezone.timedelta(days=1)
        )
        response = self.client.patch(
            url("admin_exam_detail", exam.pk),
            {"status": "published"},
            content_type="application/json",
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("result_publish_time", response.json()["errors"])

    def test_touching_its_times_still_applies_the_rule(self):
        exam = self.published_exam()
        later = (timezone.now() + timezone.timedelta(days=2)).isoformat()
        response = self.client.patch(
            url("admin_exam_detail", exam.pk),
            {"result_publish_time": later},
            content_type="application/json",
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 422)


class RankingQueryTests(CourseExamTestCase):
    """The student ranking is ranked in the database and agrees with the admin's ranking."""

    def setUp(self):
        super().setUp()
        self.exam = self.published_exam(questions=1)
        start = timezone.now() - timezone.timedelta(hours=1)
        # (score, minutes taken): two tie on both and share a rank.
        results = [(1, 10), (1, 5), (0, 3), (1, 10), (Decimal("-0.25"), 1)]
        self.users = []
        for score, minutes in results:
            user = make_user()
            Enrollment.objects.create(course=self.course, user=user)
            ExamAttempt.objects.create(
                exam=self.exam,
                user=user,
                seed=1,
                started_at=start,
                submitted_at=start + timezone.timedelta(minutes=minutes),
                status=ExamAttempt.Status.SUBMITTED,
                score=score,
                is_official=True,
            )
            self.users.append(user)

    def test_ranks_match_the_admin_ranking_ties_included(self):
        expected = selectors.official_ranks(self.exam)
        total, top, _mine = selectors.ranking(self.exam, self.student, size=10)
        self.assertEqual(total, 5)
        self.assertEqual({attempt.pk: attempt.rank for attempt in top}, expected)
        self.assertEqual([attempt.rank for attempt in top], [1, 2, 2, 4, 5])

    def test_the_viewer_outside_the_top_still_gets_their_rank(self):
        expected = selectors.official_ranks(self.exam)
        for user in self.users:
            with self.subTest(user=user.pk):
                _total, top, mine = selectors.ranking(self.exam, user, size=1)
                self.assertEqual(len(top), 1)
                self.assertEqual(mine.rank, expected[mine.pk])

    def test_the_page_reads_a_fixed_number_of_rows(self):
        """The top rows, the viewer's row, their place and the total -- however many sat the exam."""
        with self.assertNumQueries(4):
            selectors.ranking(self.exam, self.users[-1], size=2)


class SubmissionsPageTests(RankingQueryTests):
    """The admin submissions table, a page at a time, ranked against everyone."""

    def page(self, **params):
        url = reverse("api:exam:admin_exam_attempts", args=[self.exam.pk])
        return self.client.get(url, params, **self.admin_auth).json()

    def test_a_later_page_carries_the_ranks_of_the_whole_exam(self):
        first, second = self.page(per_page=2), self.page(per_page=2, page=2)
        self.assertEqual(first["meta"]["total"], 5)
        self.assertEqual([row["rank"] for row in first["data"]], [1, 2])
        self.assertEqual([row["rank"] for row in second["data"]], [2, 4])
        self.assertEqual(first["summary"], second["summary"])

    def test_the_table_runs_in_rank_order_when_scores_tie(self):
        """Ranked by time taken, not by when each was submitted: page 1 must hold the top ranks."""
        start = timezone.now() - timezone.timedelta(hours=2)
        # Submitted last but quickest: ranks first among the ties.
        late_and_quick = ExamAttempt.objects.create(
            exam=self.exam,
            user=make_user(),
            seed=1,
            status=ExamAttempt.Status.SUBMITTED,
            score=1,
            is_official=True,
            started_at=start + timezone.timedelta(minutes=90),
            submitted_at=start + timezone.timedelta(minutes=91),
        )
        rows = self.page(per_page=50)["data"]
        ranks = [row["rank"] for row in rows if row["is_official"]]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(rows[0]["id"], late_and_quick.pk)

    def test_the_summary_counts_every_official_result(self):
        summary = self.page(per_page=1)["summary"]
        # DRF's JSON encoder writes a Decimal as a number, so read it back through its text.
        self.assertEqual((summary["submitted"], Decimal(str(summary["highest"]))), (5, Decimal("1")))
        self.assertEqual(Decimal(str(summary["average"])), Decimal("0.55"))

    def test_the_page_costs_the_same_however_many_sat_the_exam(self):
        url = reverse("api:exam:admin_exam_attempts", args=[self.exam.pk])
        self.client.get(url, {"per_page": 2}, **self.admin_auth)
        with CaptureQueriesContext(connection) as few:
            self.client.get(url, {"per_page": 2}, **self.admin_auth)
        start = timezone.now() - timezone.timedelta(hours=1)
        for _ in range(20):
            ExamAttempt.objects.create(
                exam=self.exam,
                user=make_user(),
                seed=1,
                started_at=start,
                submitted_at=start,
                status=ExamAttempt.Status.SUBMITTED,
                score=1,
                is_official=True,
            )
        with CaptureQueriesContext(connection) as many:
            response = self.client.get(url, {"per_page": 2}, **self.admin_auth)
        self.assertEqual(len(response.json()["data"]), 2)
        self.assertEqual(len(many), len(few))


class FinalizeCommandTests(CourseExamTestCase):
    def test_expired_attempts_are_finalized_reading_each_paper_once(self):
        exam = self.published_exam(questions=2)
        for user in (self.student, self.other):
            attempt_service.start_attempt(exam, user)
        ExamAttempt.objects.update(deadline=timezone.now() - timezone.timedelta(minutes=1))

        out = StringIO()
        with mock.patch.object(attempt_service, "paper_key", wraps=grading.paper_key) as reads:
            call_command("finalize_exam_attempts", stdout=out)

        self.assertIn("2 attempt(s) finalized", out.getvalue())
        self.assertEqual(reads.call_count, 1)
        self.assertFalse(ExamAttempt.objects.in_progress().exists())

    def test_one_broken_attempt_does_not_stall_the_rest(self):
        exam = self.published_exam(questions=1)
        broken = attempt_service.start_attempt(exam, self.student)
        attempt_service.start_attempt(exam, self.other)
        ExamAttempt.objects.update(deadline=timezone.now() - timezone.timedelta(minutes=1))
        real_complete = attempt_service.complete_lesson

        def complete(*, user, content):
            if user == self.student:
                raise RuntimeError("lesson progress is broken for this student")
            return real_complete(user=user, content=content)

        out = StringIO()
        with (
            mock.patch.object(attempt_service, "complete_lesson", side_effect=complete),
            self.assertLogs("apps.exam.services.attempts", level="ERROR"),
        ):
            call_command("finalize_exam_attempts", stdout=out)

        self.assertIn("1 attempt(s) finalized", out.getvalue())
        self.assertEqual(ExamAttempt.objects.get(user=self.other).status, ExamAttempt.Status.SUBMITTED)
        broken.refresh_from_db()
        self.assertEqual(broken.status, ExamAttempt.Status.IN_PROGRESS)
