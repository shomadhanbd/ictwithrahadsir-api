from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.academic.models import ClassLevel
from apps.core.testing import bearer, make_user
from apps.courses.models import Course, Enrollment
from apps.feedback.models import Feedback
from apps.identity.models import User
from apps.profiles.models import StudentProfile

LIST_URL = reverse("api:feedback:feedback_list")
RATING_URL = reverse("api:feedback:course_rating")
GENERAL_URL = reverse("api:feedback:my_general_feedback")
ADMIN_URL = reverse("api:feedback:admin_feedback_list")
HOME_URL = reverse("api:website:home")


def course_url(course):
    return reverse("api:feedback:my_course_feedback", args=[course.slug])


class FeedbackTestCase(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title="ICT", slug="ict-feedback", status="published")
        self.student = make_user(name="Sadia")
        self.auth = bearer(self.student)
        self.admin = bearer(make_user(role=User.Role.ADMIN))

    def enrol(self, user=None, **fields):
        return Enrollment.objects.create(course=self.course, user=user or self.student, **fields)

    def approve(self, feedback_id, **fields):
        url = reverse("api:feedback:admin_feedback_detail", args=[feedback_id])
        return self.client.patch(url, {"status": "approved", **fields}, format="json", **self.admin)


class StudentFeedbackTests(FeedbackTestCase):
    def test_course_feedback_waits_for_approval_then_is_listed(self):
        self.enrol()
        response = self.client.put(course_url(self.course), {"rating": 4, "comment": "ভালো"}, format="json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(self.client.get(LIST_URL, {"course": self.course.slug}).json()["data"], [])

        self.assertEqual(self.approve(response.json()["id"]).status_code, 200)
        rows = self.client.get(LIST_URL, {"course": self.course.slug}).json()["data"]
        self.assertEqual([(row["name"], row["rating"]) for row in rows], [("Sadia", 4)])
        self.assertEqual(rows[0]["course"], {"slug": self.course.slug, "title": "ICT"})

    def test_a_past_student_may_rate_but_a_stranger_may_not(self):
        self.enrol(valid_till=timezone.now() - timezone.timedelta(days=1))
        body = {"rating": 5, "comment": "Great"}
        self.assertEqual(self.client.put(course_url(self.course), body, format="json", **self.auth).status_code, 200)
        stranger = bearer(make_user())
        response = self.client.put(course_url(self.course), body, format="json", **stranger)
        self.assertEqual(response.status_code, 422)
        self.assertIn("course", response.json()["errors"])

    def test_editing_keeps_one_row_and_asks_for_approval_again(self):
        self.enrol()
        first = self.client.put(course_url(self.course), {"rating": 5, "comment": "A"}, format="json", **self.auth)
        self.approve(first.json()["id"], is_featured=True)
        again = self.client.put(course_url(self.course), {"rating": 3, "comment": "B"}, format="json", **self.auth)
        self.assertEqual(again.json()["id"], first.json()["id"])
        feedback = Feedback.objects.get()
        self.assertEqual((feedback.rating, feedback.status, feedback.is_featured), (3, "pending", False))

    def test_general_feedback_is_one_per_student_and_can_be_withdrawn(self):
        profile = StudentProfile.objects.get_or_create(user=self.student)[0]
        profile.class_level = ClassLevel.objects.create(name="HSC", slug="hsc-feedback")
        profile.institution = "Sylhet Govt College"
        profile.save()
        self.assertEqual(self.client.get(GENERAL_URL, **self.auth).status_code, 404)
        for comment in ("One", "Two"):
            self.client.put(GENERAL_URL, {"rating": 5, "comment": comment}, format="json", **self.auth)
        feedback = Feedback.objects.get(source="general")
        self.assertEqual((feedback.comment, feedback.designation), ("Two", "HSC · Sylhet Govt College"))
        self.assertEqual(self.client.get(GENERAL_URL, **self.auth).json()["comment"], "Two")

        self.assertEqual(self.client.delete(GENERAL_URL, **self.auth).status_code, 204)
        self.assertFalse(Feedback.objects.exists())

    def test_a_student_without_a_name_is_never_shown_by_phone(self):
        User.objects.filter(pk=self.student.pk).update(name="")
        self.client.put(GENERAL_URL, {"rating": 5, "comment": "Hi"}, format="json", **self.auth)
        self.assertEqual(Feedback.objects.get().name, "শিক্ষার্থী")

    def test_a_rating_must_be_one_to_five(self):
        response = self.client.put(GENERAL_URL, {"rating": 6, "comment": "Hi"}, format="json", **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertIn("rating", response.json()["errors"])

    def test_visitors_cannot_write_feedback(self):
        self.assertEqual(self.client.put(GENERAL_URL, {"rating": 5, "comment": "Hi"}, format="json").status_code, 401)


class CourseRatingTests(FeedbackTestCase):
    def test_the_summary_counts_only_approved_feedback(self):
        for rating, status in ((5, "approved"), (4, "approved"), (1, "pending")):
            Feedback.objects.create(
                source="course", course=self.course, name="S", rating=rating, comment="c", status=status
            )
        body = self.client.get(RATING_URL, {"course": self.course.slug}).json()
        self.assertEqual((body["average"], body["count"]), (4.5, 2))
        self.assertEqual(body["distribution"], {"5": 1, "4": 1, "3": 0, "2": 0, "1": 0})

    def test_a_course_without_feedback_has_no_average(self):
        body = self.client.get(RATING_URL, {"course": self.course.slug}).json()
        self.assertEqual((body["average"], body["count"]), (None, 0))

    def test_an_unknown_course_is_a_422(self):
        self.assertEqual(self.client.get(RATING_URL, {"course": "nope"}).status_code, 422)


class AdminFeedbackTests(FeedbackTestCase):
    def test_staff_add_feedback_received_elsewhere_already_approved(self):
        body = {"source": "general", "name": "Arif", "rating": 5, "comment": "Facebook review"}
        response = self.client.post(ADMIN_URL, body, format="json", **self.admin)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()["status"], response.json()["author"]), ("approved", None))

    def test_course_feedback_names_its_course(self):
        body = {"source": "course", "name": "Arif", "rating": 5, "comment": "c"}
        response = self.client.post(ADMIN_URL, body, format="json", **self.admin)
        self.assertEqual(response.status_code, 422)
        self.assertIn("course_id", response.json()["errors"])
        ok = self.client.post(ADMIN_URL, {**body, "course_id": self.course.pk}, format="json", **self.admin)
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_only_approved_feedback_can_be_featured(self):
        feedback = Feedback.objects.create(source="general", name="S", rating=5, comment="c")
        url = reverse("api:feedback:admin_feedback_detail", args=[feedback.pk])
        response = self.client.patch(url, {"is_featured": True}, format="json", **self.admin)
        self.assertEqual(response.status_code, 422)
        self.assertIn("is_featured", response.json()["errors"])

    def test_a_students_feedback_stays_on_its_course(self):
        self.enrol()
        feedback_id = self.client.put(
            course_url(self.course), {"rating": 5, "comment": "c"}, format="json", **self.auth
        ).json()["id"]
        url = reverse("api:feedback:admin_feedback_detail", args=[feedback_id])
        response = self.client.patch(url, {"source": "general", "course_id": None}, format="json", **self.admin)
        self.assertEqual(response.status_code, 422)
        self.assertIn("source", response.json()["errors"])

    def test_staff_filter_by_status(self):
        Feedback.objects.create(source="general", name="Waiting", rating=5, comment="c")
        Feedback.objects.create(source="general", name="Shown", rating=5, comment="c", status="approved")
        rows = self.client.get(ADMIN_URL, {"status": "pending"}, **self.admin).json()["data"]
        self.assertEqual([row["name"] for row in rows], ["Waiting"])

    def test_moderators_manage_it_and_students_do_not(self):
        self.assertEqual(self.client.get(ADMIN_URL, **bearer(make_user(role=User.Role.MODERATOR))).status_code, 200)
        self.assertEqual(self.client.get(ADMIN_URL, **self.auth).status_code, 403)

    def test_the_home_page_shows_only_featured_approved_feedback(self):
        Feedback.objects.create(
            source="general", name="Featured", rating=5, comment="Great", status="approved", is_featured=True
        )
        Feedback.objects.create(source="general", name="Approved", rating=5, comment="c", status="approved")
        Feedback.objects.create(source="general", name="Pending", rating=5, comment="c")
        testimonials = self.client.get(HOME_URL).json()["testimonials"]
        self.assertEqual(
            testimonials,
            [
                {
                    "id": testimonials[0]["id"],
                    "name": "Featured",
                    "designation": "",
                    "description": "Great",
                    "ratings": 5,
                    "image": None,
                }
            ],
        )


class TestimonialMigrationTests(TransactionTestCase):
    """Testimonials from `content` arrive as approved, featured general feedback."""

    before = [("feedback", "0001_initial")]
    after = [("feedback", "0002_copy_testimonials")]

    def test_each_testimonial_becomes_featured_feedback(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        # The retired `content` app's table, as an old database still has it.
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE content_testimonial (id integer PRIMARY KEY, name varchar(150), "
                "designation varchar(150), "
                "description text, ratings smallint, image varchar(200), created_at timestamp)"
            )
            cursor.execute(
                "INSERT INTO content_testimonial VALUES (1, 'Nusrat', 'HSC 2024', 'Great', 0, NULL, %s)",
                [timezone.now()],
            )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        feedback = new.get_model("feedback", "Feedback").objects.get()
        self.assertEqual(
            (feedback.source, feedback.name, feedback.comment, feedback.rating, feedback.image),
            ("general", "Nusrat", "Great", 5, ""),
        )
        self.assertEqual((feedback.status, feedback.is_featured, feedback.author_id), ("approved", True, None))

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
