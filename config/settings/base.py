"""
Settings shared by every environment.

Configuration is environment-driven (12-factor style) so the same codebase
runs unmodified in local dev, Docker, and any PaaS/VPS target. Never import
this module directly -- use `config.settings.local` or
`config.settings.production`, which import everything from here and override
only what actually differs.
"""

from pathlib import Path

import environ

# config/settings/base.py -> config/settings -> config -> <project root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-change-me-in-production-8%lw(b2e&r-3#26ob2w+v!-m6",
)
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"] if DEBUG else [])

# Both existing frontends call routes with no trailing slash (Laravel
# convention), so disable Django's default slash-redirect behavior.
APPEND_SLASH = False

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
]

LOCAL_APPS = [
    "apps.core",
    "apps.identity",
    "apps.team",
    "apps.courses",
    "apps.exams",
    "apps.shop",
    "apps.cms",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.MethodOverrideMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
#
# DATABASE_URL is the standard way to configure this (postgres://... in
# docker-compose/production). Falls back to local SQLite so the project runs
# with zero external services for quick local development.
# ---------------------------------------------------------------------------

_database_url = env("DATABASE_URL", default="") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {"default": environ.Env.db_url_config(_database_url)}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "identity.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Dhaka")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# File storage backend: local disk by default (zero-config dev/small deploys).
# Set USE_S3=True + the AWS_* / DO Spaces env vars to switch to S3-compatible
# object storage (DigitalOcean Spaces, AWS S3, etc.) with no code changes.
USE_S3 = env.bool("USE_S3", default=False)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

if USE_S3:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="sgp1")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="")
    AWS_DEFAULT_ACL = "public-read"
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    STORAGES["default"] = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}
else:
    STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# CORS
#
# Both frontends (client + admin) call this API cross-origin. The client's
# BFF forwards a bearer token (no cookies needed against this API), so we do
# not need CORS_ALLOW_CREDENTIALS for it; kept permissive-by-allowlist.
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOWED_ORIGIN_REGEXES = env.list("CORS_ALLOWED_ORIGIN_REGEXES", default=[])
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=DEBUG)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.core.api.authentication.BearerTokenAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.LaravelStylePageNumberPagination",
    "PAGE_SIZE": 15,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler.laravel_style_exception_handler",
    # Applied per-view via throttle_classes (see apps.core.api.throttling);
    # there is no default throttle, so ordinary reads stay unlimited.
    "DEFAULT_THROTTLE_RATES": {
        "login_burst": env("THROTTLE_LOGIN_BURST", default="10/min"),
        "login_sustained": env("THROTTLE_LOGIN_SUSTAINED", default="100/hour"),
        "auth_burst": env("THROTTLE_AUTH_BURST", default="10/min"),
        "auth_sustained": env("THROTTLE_AUTH_SUSTAINED", default="60/hour"),
    },
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ---------------------------------------------------------------------------
# Cache
#
# This backs the auth rate limits, so it matters in production: the default
# LocMemCache is per-process, and the container runs gunicorn with 3
# workers, which means each worker keeps its own throttle counter and the
# effective limit is roughly 3x whatever is configured (and resets on every
# deploy). Point CACHE_URL at a shared Redis to make the limits real:
#
#     CACHE_URL=redis://redis:6379/1        (needs `pip install redis`)
# ---------------------------------------------------------------------------

_cache_url = env("CACHE_URL", default="")
if _cache_url:
    CACHES = {"default": env.cache_url("CACHE_URL")}
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "shomadhan-local",
        }
    }

# ---------------------------------------------------------------------------
# Logging
#
# Created at import time so a fresh checkout never fails on a missing
# directory. `*.log` is already gitignored.
# ---------------------------------------------------------------------------

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "debug.log"),
            "maxBytes": 25 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
    "loggers": {
        # Routine 4xx are part of normal API life; without this every
        # validation error would land in the log as a warning.
        "django.request": {
            "handlers": ["console", "file"],
            "level": "ERROR",
            "propagate": False,
        },
        # Per-request access lines are noise in a file that exists to hold
        # application events.
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Platform-specific settings
# ---------------------------------------------------------------------------

# OTP / SMS gateway. SMS_BACKEND="console" (default) logs OTPs instead of
# sending real SMS -- swap to a real provider later by implementing
# apps.core.services.factory.base.SmsBackend and pointing SMS_BACKEND at it.
SMS_BACKEND = env("SMS_BACKEND", default="console")
OTP_LENGTH = env.int("OTP_LENGTH", default=6)
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=5 * 60)
OTP_RESEND_COOLDOWN_SECONDS = env.int("OTP_RESEND_COOLDOWN_SECONDS", default=60)

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")
ADMIN_FRONTEND_URL = env("ADMIN_FRONTEND_URL", default="http://localhost:3001")

# Manual mobile-banking payment recipient number shown to students at checkout.
PAYMENT_RECEIVE_NUMBER = env("PAYMENT_RECEIVE_NUMBER", default="01711778602")
