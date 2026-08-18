"""Shared test helpers."""

from django.core.cache import cache

from rest_framework.test import APITestCase


class ThrottledAPITestCase(APITestCase):
    """Base case for suites that exercise a rate-limited endpoint.

    DRF keeps throttle history in the default cache keyed by client IP, and
    every test in a run shares both. Without clearing it between tests, the
    tenth request in a class trips a limit set for real traffic and the
    failure lands on whichever test happens to run tenth.
    """

    def setUp(self):
        cache.clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        cache.clear()
