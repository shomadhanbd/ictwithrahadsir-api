"""Production settings. Default for `wsgi.py` / `asgi.py`.

`manage.py` defaults to `local`, so set DJANGO_SETTINGS_MODULE=config.settings.production
when running migrations, collectstatic or cron commands on the server.
"""

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *  # noqa: F403
from config.settings.base import env

DEBUG = False


def _required(name):
    value = env(name, default="")
    if not value:
        raise ImproperlyConfigured(f"Set {name}: production has no fallback for it.")
    return value


def _required_https(name):
    value = _required(name)
    if not value.startswith("https://"):
        raise ImproperlyConfigured(f"{name} must be a public https:// URL, not {value!r}.")
    return value


# Required settings: each one fails the boot instead of falling back to a dev default.

SECRET_KEY = _required("SECRET_KEY")
if SECRET_KEY.startswith(("django-insecure", "change-me")):
    raise ImproperlyConfigured("SECRET_KEY is still a placeholder.")

DATABASES = {"default": env.db_url_config(_required("DATABASE_URL"))}
# Reuse connections across requests instead of opening one per request.
DATABASES["default"].update(CONN_MAX_AGE=60, CONN_HEALTH_CHECKS=True)
if "sqlite" in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured("DATABASE_URL must point at Postgres, not SQLite.")

# The console backend writes OTP codes to the log.
SMS_BACKEND = _required("SMS_BACKEND")
if SMS_BACKEND != "bulksmsbd":
    raise ImproperlyConfigured("SMS_BACKEND must be bulksmsbd in production.")
# Without them every OTP fails: nobody could sign up, sign in by code or reset a password.
BULKSMSBD_API_KEY = _required("BULKSMSBD_API_KEY")
BULKSMSBD_SENDER_ID = _required("BULKSMSBD_SENDER_ID")

# The admin panel calls the API from the browser, so its origin must be listed; the website goes through its server.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("Set CORS_ALLOWED_ORIGINS to the admin panel's https:// origin.")
if any(not origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS):
    raise ImproperlyConfigured(f"CORS_ALLOWED_ORIGINS must all be https://, not {CORS_ALLOWED_ORIGINS!r}.")

API_BASE_URL = _required_https("API_BASE_URL")
FRONTEND_URL = _required_https("FRONTEND_URL")

SSLCOMMERZ_STORE_ID = _required("SSLCOMMERZ_STORE_ID")
SSLCOMMERZ_STORE_PASSWORD = _required("SSLCOMMERZ_STORE_PASSWORD")
SSLCOMMERZ_SUCCESS_REDIRECT = _required_https("SSLCOMMERZ_SUCCESS_REDIRECT")
SSLCOMMERZ_FAIL_REDIRECT = _required_https("SSLCOMMERZ_FAIL_REDIRECT")
SSLCOMMERZ_CANCEL_REDIRECT = _required_https("SSLCOMMERZ_CANCEL_REDIRECT")

# Uploads: the folder the web server serves at /media/ (README, "Uploaded files").
MEDIA_ROOT = _required("MEDIA_ROOT")
if not MEDIA_ROOT.startswith("/"):
    raise ImproperlyConfigured(f"MEDIA_ROOT must be the absolute path served at /media/, not {MEDIA_ROOT!r}.")
# Readable by the web server's user, whichever user gunicorn writes them as.
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# No default, so a missing value fails loudly.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# Transport security: assumes TLS ends at a proxy that sets X-Forwarded-Proto.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Browsers cache HSTS for its full duration, so raise it only once HTTPS is stable.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)

# Log to stdout: several gunicorn workers can't share one rotating file.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
