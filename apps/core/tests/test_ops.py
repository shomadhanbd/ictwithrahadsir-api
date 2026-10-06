"""Health probe, log hygiene and the settings that fail closed."""

from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from rest_framework.permissions import IsAuthenticated
from rest_framework.settings import api_settings

from apps.core.phones import masked_phone
from apps.core.sms import BulkSmsBdBackend
from apps.core.tests.test_production_settings import load_production

HEALTH_URL = "/api/health/"


class HealthCheckTests(TestCase):
    def test_it_answers_without_a_token(self):
        response = self.client.get(HEALTH_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "database": True, "cache": True})

    @override_settings(ALLOWED_HOSTS=["api.example.com"], SECURE_SSL_REDIRECT=True)
    def test_a_load_balancer_probing_by_ip_over_http_gets_an_answer(self):
        response = self.client.get(HEALTH_URL, HTTP_HOST="10.0.0.7")
        self.assertEqual(response.status_code, 200)

    def test_it_reports_a_dead_cache_as_503(self):
        with mock.patch("apps.core.api.health.cache.set", side_effect=ConnectionError("redis down")):
            response = self.client.get(HEALTH_URL)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["cache"])


class LogHygieneTests(SimpleTestCase):
    def test_a_logged_phone_is_masked(self):
        self.assertEqual(masked_phone("01810001111"), "018******11")
        self.assertEqual(masked_phone(None), "***")

    def test_the_sms_gateway_log_carries_no_full_number(self):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"response_code": 202}
        with (
            mock.patch("apps.core.sms.requests.post", return_value=reply),
            self.assertLogs("sms", level="INFO") as logs,
        ):
            BulkSmsBdBackend().send("01810001111", "code 123456")
        self.assertNotIn("01810001111", "\n".join(logs.output))


class FailClosedSettingsTests(SimpleTestCase):
    def test_a_view_that_forgets_its_permissions_requires_sign_in(self):
        self.assertEqual(api_settings.DEFAULT_PERMISSION_CLASSES, [IsAuthenticated])

    def test_production_logs_to_stdout_only(self):
        handlers = load_production().LOGGING["handlers"]
        self.assertEqual(list(handlers), ["console"])

    def test_the_test_run_uses_a_fast_hasher(self):
        self.assertEqual(settings.PASSWORD_HASHERS, ["django.contrib.auth.hashers.MD5PasswordHasher"])
