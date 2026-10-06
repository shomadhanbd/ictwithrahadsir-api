"""Behaviour of the shared DRF/model plumbing in `apps.core`."""

from django.test import TestCase

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Course
from apps.identity.models import User


class TypedSlugTests(APITestCase):
    """Slugs are typed by staff; the API refuses a missing or taken one."""

    def setUp(self):
        self.auth = bearer(make_user(role=User.Role.ADMIN))

    def post(self, **payload):
        return self.client.post("/api/private/courses/", {"title": "ICT", **payload}, format="json", **self.auth)

    def test_a_slug_is_required(self):
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertIn("slug", response.json()["errors"])

    def test_a_taken_slug_is_refused(self):
        Course.objects.create(slug="ict", title="Existing")
        response = self.post(slug="ict")
        self.assertEqual(response.status_code, 422)
        self.assertIn("slug", response.json()["errors"])

    def test_the_typed_slug_is_kept_when_the_title_changes(self):
        course = Course.objects.create(slug="biology", title="Biology")
        course.title = "Biology Revised"
        course.save()
        course.refresh_from_db()
        self.assertEqual(course.slug, "biology")


class PaginationTests(APITestCase):
    """Lists answer `{data, meta}` with only the keys the frontends read."""

    @classmethod
    def setUpTestData(cls):
        for i in range(12):
            Course.objects.create(slug=next_slug("course"), title=f"Course {i}", status="published")

    def test_the_envelope(self):
        body = self.client.get("/api/public/courses/?per_page=5&page=2").data
        self.assertEqual(list(body.keys()), ["data", "meta"])
        self.assertEqual(
            body["meta"],
            {"current_page": 2, "last_page": 3, "per_page": 5, "total": 12, "from": 6, "to": 10},
        )
        self.assertEqual(len(body["data"]), 5)

    def test_per_page_is_capped_at_200(self):
        self.assertEqual(self.client.get("/api/public/courses/?per_page=1000").data["meta"]["per_page"], 200)

    def test_an_empty_list_has_no_range(self):
        Course.objects.all().delete()
        meta = self.client.get("/api/public/courses/").data["meta"]
        self.assertEqual((meta["total"], meta["from"], meta["to"], meta["last_page"]), (0, None, None, 1))


class MediaFieldTests(TestCase):
    def test_a_link_longer_than_the_column_is_a_422_not_a_500(self):
        from apps.core.api.serializers.fields import MediaField

        field = MediaField()
        self.assertEqual(field.run_validation("https://example.com/" + "a" * 100), "https://example.com/" + "a" * 100)
        with self.assertRaisesMessage(Exception, "at most 200 characters"):
            field.run_validation("https://example.com/" + "a" * 200)
