"""The course picker every staff member's forms share."""

from django.urls import reverse

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Course
from apps.identity.models import User

LOOKUP_URL = reverse("api:courses:admin_course_lookup")


class CourseLookupTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.auth = bearer(make_user(role=User.Role.MODERATOR))
        for title in ("HSC ICT", "SSC ICT", "HSC Physics"):
            Course.objects.create(title=title, slug=next_slug("course"))

    def titles(self, **params):
        response = self.client.get(LOOKUP_URL, params, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return [course["title"] for course in response.json()["data"]]

    def test_courses_come_by_title(self):
        self.assertEqual(self.titles(), ["HSC ICT", "HSC Physics", "SSC ICT"])

    def test_a_search_matches_the_title(self):
        self.assertEqual(self.titles(search="ict"), ["HSC ICT", "SSC ICT"])

    def test_each_choice_is_only_an_id_and_a_title(self):
        course = self.client.get(LOOKUP_URL, **self.auth).json()["data"][0]
        self.assertEqual(set(course), {"id", "title"})

    def test_at_most_twenty_are_returned(self):
        for _ in range(25):
            Course.objects.create(title="Extra", slug=next_slug("course"))
        self.assertEqual(len(self.titles()), 20)
