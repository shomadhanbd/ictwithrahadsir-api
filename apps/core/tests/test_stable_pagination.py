"""Paginated admin lists that aggregate keep a stable order, so no row repeats or goes missing across pages."""

import warnings

from django.core.paginator import UnorderedObjectListWarning

from rest_framework.test import APITestCase

from apps.academic.models import ClassLevel, Group, Subject
from apps.core.testing import bearer, make_user
from apps.courses.models import Course
from apps.identity.models import User


class StablePaginationTests(APITestCase):
    def setUp(self):
        self.auth = bearer(make_user(role=User.Role.ADMIN))
        level, group = ClassLevel.objects.create(name="HSC"), Group.objects.create(name="Science")
        for i in range(3):
            Course.objects.create(title=f"Course {i}", slug=f"stable-{i}")
            Subject.objects.create(name=f"Subject {i}", class_level=level, group=group)

    def test_the_lists_are_ordered(self):
        for url in ("/api/private/courses/", "/api/private/subjects/"):
            with self.subTest(url=url), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                response = self.client.get(url, {"per_page": 2}, **self.auth)
            self.assertEqual(response.status_code, 200)
            self.assertFalse([w for w in caught if issubclass(w.category, UnorderedObjectListWarning)])

    def test_the_counted_querysets_keep_the_model_order(self):
        for queryset in (Course.objects.with_enrolled_count(), Subject.objects.with_counts()):
            with self.subTest(model=queryset.model.__name__):
                self.assertTrue(queryset.ordered)
                self.assertEqual(queryset.query.order_by[-1], "pk")
