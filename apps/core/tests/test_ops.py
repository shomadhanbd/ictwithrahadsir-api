"""Log hygiene and the settings that fail closed."""

from django.conf import settings
from django.test import SimpleTestCase

from rest_framework.permissions import IsAuthenticated
from rest_framework.settings import api_settings

from apps.core.tests.test_production_settings import load_production
from apps.core.text.phones import masked_phone


class LogHygieneTests(SimpleTestCase):
    def test_a_logged_phone_is_masked(self):
        self.assertEqual(masked_phone("01810001111"), "018******11")
        self.assertEqual(masked_phone(None), "***")


class FailClosedSettingsTests(SimpleTestCase):
    def test_a_view_that_forgets_its_permissions_requires_sign_in(self):
        self.assertEqual(api_settings.DEFAULT_PERMISSION_CLASSES, [IsAuthenticated])

    def test_production_logs_to_stdout_only(self):
        handlers = load_production().LOGGING["handlers"]
        self.assertEqual(list(handlers), ["console"])

    def test_the_test_run_uses_a_fast_hasher(self):
        self.assertEqual(settings.PASSWORD_HASHERS, ["django.contrib.auth.hashers.MD5PasswordHasher"])
