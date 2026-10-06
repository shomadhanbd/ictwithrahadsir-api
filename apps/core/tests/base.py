"""Shared test helpers."""

from django.core.cache import cache

from rest_framework.test import APITestCase


class ThrottledAPITestCase(APITestCase):
    """Base case for suites that exercise a rate-limited endpoint."""

    def setUp(self):
        cache.clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        cache.clear()
