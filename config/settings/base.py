"""Settings shared by every environment, read from env vars / `.env`.

Don't point DJANGO_SETTINGS_MODULE here; use `local` or `production`.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# Core

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production-8%lw(b2e&r-3#26ob2w+v!-m6")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"] if DEBUG else [])

# Routes end in a slash; a slash-less request 404s instead of redirecting.
APPEND_SLASH = False

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Applications

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
    "drf_spectacular",
    "phonenumber_field",
]

LOCAL_APPS = [
    "apps.core",
    "apps.academic",
    "apps.question",
    "apps.profiles",
    "apps.identity",
    "apps.courses",
    "apps.exam",
    "apps.billing",
    "apps.content",
    "apps.demo",
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

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project templates override contrib.admin's (e.g. admin/base_site.html).
        "DIRS": [BASE_DIR / "templates"],
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

# Database: DATABASE_URL, else a local SQLite file.

DATABASES = {
    "default": environ.Env.db_url_config(env("DATABASE_URL", default="") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

# Cache: backs the auth rate limits. The per-process default gives each
# gunicorn worker its own counter, so production should set CACHE_URL=redis://...

CACHES = {"default": environ.Env.cache_url_config(env("CACHE_URL", default="") or "locmemcache://shomadhan-local")}

# Auth

AUTH_USER_MODEL = "identity.User"
PHONENUMBER_DEFAULT_REGION = "BD"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# i18n

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Dhaka")
USE_I18N = True
USE_TZ = True

# Static and media files. Media is only the demo images `seed_demo` writes.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# CORS

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOWED_ORIGIN_REGEXES = env.list("CORS_ALLOWED_ORIGIN_REGEXES", default=[])
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=DEBUG)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.api.authentication.BearerTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.LaravelStylePageNumberPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler.laravel_style_exception_handler",
    # Opt-in per view (apps.core.api.throttling); there is no default throttle.
    "DEFAULT_THROTTLE_RATES": {
        "login_burst": env("THROTTLE_LOGIN_BURST", default="10/min"),
        "login_sustained": env("THROTTLE_LOGIN_SUSTAINED", default="100/hour"),
        "auth_burst": env("THROTTLE_AUTH_BURST", default="10/min"),
        "auth_sustained": env("THROTTLE_AUTH_SUSTAINED", default="60/hour"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Shomadhan Coaching API",
    "DESCRIPTION": (
        "Backend for the Shomadhan Coaching platform, split by audience: "
        "/api/public/* is the client site, /api/private/* is the back-office "
        "panel. Every /api/private/* endpoint requires an admin, teacher or "
        "moderator token, and each one requires a specific tier: admins own "
        "accounts, payments and pricing; moderators own site content; "
        "teachers own course material, scoped to the courses they are "
        "assigned to. See apps/core/api/permissions.py."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    # Stable names for choice sets shared across fields, which spectacular
    # would otherwise name with a hash ("Status91dEnum").
    "ENUM_NAME_OVERRIDES": {
        "ExamStatusEnum": "apps.exam.models.Exam.Status",
        "PaymentStatusEnum": "apps.billing.models.Payment.Status",
        "OrderStatusEnum": "apps.billing.models.Order.Status",
        "ContentTypeEnum": "apps.courses.models.Content.Type",
        "QuestionTypeEnum": "apps.question.models.Question.Type",
    },
}

# Logging

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
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
        # Keep routine 4xx and per-request access lines out of the log file.
        "django.request": {"handlers": ["console", "file"], "level": "ERROR", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# SMS and OTP (providers in apps/core/sms.py)

SMS_BACKEND = env("SMS_BACKEND", default="console")
BULKSMSBD_API_KEY = env("BULKSMSBD_API_KEY", default="")
BULKSMSBD_SENDER_ID = env("BULKSMSBD_SENDER_ID", default="")
SMS_OTP_TEMPLATE = env("SMS_OTP_TEMPLATE", default="Your ICT with Rahad Sir verification code is {code}")

OTP_LENGTH = env.int("OTP_LENGTH", default=6)
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=5 * 60)
OTP_RESEND_COOLDOWN_SECONDS = env.int("OTP_RESEND_COOLDOWN_SECONDS", default=60)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RATE_LIMIT_PER_PHONE_PER_HOUR = env.int("OTP_RATE_LIMIT_PER_PHONE_PER_HOUR", default=5)
# How long a verified phone may take to finish registering.
REGISTRATION_WINDOW_SECONDS = env.int("REGISTRATION_WINDOW_SECONDS", default=30 * 60)

# Store-review account: DEMO_PHONE skips the SMS and accepts DEMO_OTP_CODE.
# Off by default, since a fixed code is a backdoor.
DEMO_PHONE = env("DEMO_PHONE", default="")
DEMO_OTP_CODE = env("DEMO_OTP_CODE", default="000000")

# Payments: SSLCommerz is the only gateway (client in apps/billing/sslcommerz.py).

SSLCOMMERZ_STORE_ID = env("SSLCOMMERZ_STORE_ID", default="")
SSLCOMMERZ_STORE_PASSWORD = env("SSLCOMMERZ_STORE_PASSWORD", default="")
SSLCOMMERZ_SANDBOX = env.bool("SSLCOMMERZ_SANDBOX", default=True)
# This API's public https origin. SSLCommerz posts its callbacks here, so it is
# set explicitly rather than read off a request.
API_BASE_URL = env("API_BASE_URL", default="http://localhost:8000")
# The frontend page a student's browser returns to after paying.
PAYMENT_RESULT_URL = env("PAYMENT_RESULT_URL", default="http://localhost:3000/payment/result")
