"""Local development settings. Default for `manage.py`."""

import sys

from config.settings.base import *  # noqa: F403
from config.settings.base import BASE_DIR, LOGGING, LOGS_DIR, env

# Core

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

# Kept out of base so production has no command that writes fake data.
INSTALLED_APPS = [*INSTALLED_APPS, "apps.demo"]  # noqa: F405

# Only the demo images `seed_demo` writes; served by runserver.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Integrations

SSLCOMMERZ_IS_SANDBOX = env.bool("SSLCOMMERZ_IS_SANDBOX", default=True)

# Logging

LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Tests: a fast hasher, and nothing (OTP codes included) written to logs/debug.log.
if sys.argv[1:2] == ["test"]:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    LOGGING = {
        **LOGGING,
        "handlers": {**LOGGING["handlers"], "file": {"class": "logging.NullHandler"}},
    }
