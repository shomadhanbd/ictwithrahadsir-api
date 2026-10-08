import importlib
import os
import sys
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

import environ

SETTINGS_MODULES = ("config.settings.base", "config.settings.production")

PRODUCTION_ENV = {
    "SECRET_KEY": "k" * 50,
    "ALLOWED_HOSTS": "api.example.com",
    "SMS_BACKEND": "bulksmsbd",
    "DATABASE_URL": "postgres://app:secret@db:5432/shomadhan",
    "API_BASE_URL": "https://api.example.com",
    "SSLCOMMERZ_STORE_ID": "store",
    "SSLCOMMERZ_STORE_PASSWORD": "secret",
    "FRONTEND_URL": "https://example.com",
    "SSLCOMMERZ_SUCCESS_REDIRECT": "https://example.com/payment/success",
    "SSLCOMMERZ_FAIL_REDIRECT": "https://example.com/payment/fail",
    "SSLCOMMERZ_CANCEL_REDIRECT": "https://example.com/payment/cancel",
    "MEDIA_ROOT": "/srv/shomadhan/media",
}


def load_production(**overrides):
    """The production settings module, imported fresh against exactly this environment."""
    environment = {key: value for key, value in {**PRODUCTION_ENV, **overrides}.items() if value is not None}
    with (
        mock.patch.dict(os.environ, environment, clear=True),
        mock.patch.object(environ.Env, "read_env"),
        mock.patch.dict(sys.modules),
    ):
        for name in SETTINGS_MODULES:
            sys.modules.pop(name, None)
        return importlib.import_module("config.settings.production")


class ProductionSettingsTests(SimpleTestCase):
    def test_a_complete_environment_boots(self):
        settings = load_production()
        self.assertFalse(settings.DEBUG)

    def test_uploads_go_to_the_folder_nginx_serves_readable_by_it(self):
        settings = load_production()
        self.assertEqual(settings.MEDIA_ROOT, "/srv/shomadhan/media")
        self.assertEqual((settings.FILE_UPLOAD_PERMISSIONS, settings.FILE_UPLOAD_DIRECTORY_PERMISSIONS), (0o644, 0o755))

    def test_the_payment_gateway_is_live_unless_told_otherwise(self):
        self.assertFalse(load_production().SSLCOMMERZ_IS_SANDBOX)
        self.assertTrue(load_production(SSLCOMMERZ_IS_SANDBOX="True").SSLCOMMERZ_IS_SANDBOX)

    def test_each_development_fallback_fails_the_boot(self):
        cases = {
            "no secret key": {"SECRET_KEY": None},
            "placeholder secret key": {"SECRET_KEY": "change-me-to-a-long-random-string"},
            "no sms backend": {"SMS_BACKEND": None},
            "console sms": {"SMS_BACKEND": "console"},
            "no database": {"DATABASE_URL": None},
            "sqlite database": {"DATABASE_URL": "sqlite:///db.sqlite3"},
            "no public api origin": {"API_BASE_URL": None},
            "localhost api origin": {"API_BASE_URL": "http://localhost:8000"},
            "no store id": {"SSLCOMMERZ_STORE_ID": None},
            "no store password": {"SSLCOMMERZ_STORE_PASSWORD": None},
            "no frontend": {"FRONTEND_URL": None},
            "no success redirect": {"SSLCOMMERZ_SUCCESS_REDIRECT": None},
            "localhost frontend": {"FRONTEND_URL": "http://localhost:3000"},
            "localhost fail redirect": {"SSLCOMMERZ_FAIL_REDIRECT": "http://localhost:3000/payment/fail"},
            "no media folder": {"MEDIA_ROOT": None},
            "relative media folder": {"MEDIA_ROOT": "media"},
        }
        for label, overrides in cases.items():
            with self.subTest(label), self.assertRaises(ImproperlyConfigured):
                load_production(**overrides)
