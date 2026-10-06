"""Every /api error is the JSON envelope, never Django's HTML page."""

from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import override_settings

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user

ME_URL = "/api/public/me/"


class ErrorEnvelopeTests(APITestCase):
    def setUp(self):
        self.auth = bearer(make_user())

    def test_an_unexpected_error_is_a_logged_json_500(self):
        with (
            mock.patch("apps.identity.api.public.views.UserSerializer", side_effect=RuntimeError("bug")),
            self.assertLogs("django.request", level="ERROR") as logs,
        ):
            response = self.client.get(ME_URL, **self.auth)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"message": "Something went wrong."})
        self.assertIn("bug", "\n".join(logs.output))

    def test_a_race_on_a_unique_value_is_a_409(self):
        with mock.patch("apps.identity.api.public.views.UserSerializer", side_effect=IntegrityError("duplicate key")):
            response = self.client.get(ME_URL, **self.auth)
        self.assertEqual(response.status_code, 409)
        self.assertIn("message", response.json())

    def test_a_validation_error_without_fields_is_still_a_422(self):
        with mock.patch("apps.identity.api.public.views.UserSerializer", side_effect=ValidationError("Not allowed.")):
            response = self.client.get(ME_URL, **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"message": "Not allowed.", "errors": {"non_field_errors": ["Not allowed."]}})

    def test_an_unknown_api_url_is_a_json_404(self):
        response = self.client.get("/api/public/no-such-thing/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"message": "Not found."})

    @override_settings(DEBUG=True)
    def test_debug_still_shows_the_real_error(self):
        with (
            mock.patch("apps.identity.api.public.views.UserSerializer", side_effect=RuntimeError("bug")),
            self.assertRaises(RuntimeError),
        ):
            self.client.get(ME_URL, **self.auth)
