"""Local development settings. Default for `manage.py`."""

from config.settings.base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Every origin is welcome while developing; production narrows this to the
# CORS_ALLOWED_ORIGINS allowlist read in base.py.
CORS_ALLOW_ALL_ORIGINS = True
