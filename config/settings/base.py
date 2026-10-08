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
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Routes end in a slash; a slash-less request 404s instead of redirecting.
APPEND_SLASH = False

TIME_ZONE = "Asia/Dhaka"

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
]

LOCAL_APPS = [
    "apps.core",
    "apps.communication",
    "apps.academic",
    "apps.question",
    "apps.profiles",
    "apps.identity",
    "apps.courses",
    "apps.exam",
    "apps.billing",
    "apps.dashboard",
    "apps.uploads",
    "apps.materials",
    "apps.feedback",
    "apps.website",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Database: SQLite unless DATABASE_URL says otherwise.

DATABASES = {
    "default": environ.Env.db_url_config(env("DATABASE_URL", default="") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}


# Static files

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded files; Django serves them only under DEBUG, and in production nginx does (deploy/nginx.conf).
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# CORS and CSRF

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Lets the admin read the file name of a download (e.g. results CSV).
CORS_EXPOSE_HEADERS = ["Content-Disposition"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.api.auth.authentication.BearerTokenAuthentication"],
    # A view that forgets its permissions fails closed instead of letting anonymous users read.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.views.pagination.ApiPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.api.errors.handler.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# Auth and OTP

AUTH_USER_MODEL = "identity.User"
PHONENUMBER_DEFAULT_REGION = "BD"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

TOKEN_TTL_DAYS = 90  # signing in again after this issues a new token
REGISTRATION_WINDOW_SECONDS = 30 * 60  # a verified phone has this long to finish registering

OTP_LENGTH = 6
OTP_TTL_SECONDS = 5 * 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_RATE_LIMIT_PER_PHONE_PER_HOUR = 5

# Store-review account: DEMO_PHONE skips the SMS and accepts DEMO_OTP_CODE. Empty disables it.
DEMO_PHONE = env("DEMO_PHONE", default="")
DEMO_OTP_CODE = env("DEMO_OTP_CODE", default="000000")

# SMS (gateways in apps/communication/gateways.py)

SMS_BACKEND = env("SMS_BACKEND", default="console")
BULKSMSBD_API_KEY = env("BULKSMSBD_API_KEY", default="")
BULKSMSBD_SENDER_ID = env("BULKSMSBD_SENDER_ID", default="")
SMS_OTP_TEMPLATE = "Your ICT with Rahad Sir verification code is {code}"
EXPIRY_REMINDER_DAYS = 3  # how far ahead `send_expiry_reminders` texts the student
ACCESS_ENDED_NOTICE_DAYS = 2  # how far back it tells students their access has ended

# Payments (apps/billing/services/sslcommerz.py)

SSLCOMMERZ_IS_SANDBOX = env.bool("SSLCOMMERZ_IS_SANDBOX", default=False)
SSLCOMMERZ_STORE_ID = env("SSLCOMMERZ_STORE_ID", default="")
SSLCOMMERZ_STORE_PASSWORD = env("SSLCOMMERZ_STORE_PASSWORD", default="")
# Where the student's browser lands after the gateway; `?tran_id=` is appended.
SSLCOMMERZ_SUCCESS_REDIRECT = env("SSLCOMMERZ_SUCCESS_REDIRECT", default="http://localhost:3000/payment/success")
SSLCOMMERZ_FAIL_REDIRECT = env("SSLCOMMERZ_FAIL_REDIRECT", default="http://localhost:3000/payment/fail")
SSLCOMMERZ_CANCEL_REDIRECT = env("SSLCOMMERZ_CANCEL_REDIRECT", default="http://localhost:3000/payment/cancel")
PAYMENT_INITIATE_RATE_LIMIT_PER_USER_PER_HOUR = 10

# Public URLs

# Where SSLCommerz posts its callbacks. Set explicitly: the web app calls this API
# server-side, so a request's host is not the public one.
API_BASE_URL = env("API_BASE_URL", default="http://localhost:8000")
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")  # the student site, for links in SMS
# Shared with the student site; lets an admin edit show there at once instead of within five minutes.
WEBSITE_REVALIDATE_SECRET = env("WEBSITE_REVALIDATE_SECRET", default="")

# Logging: a rotating file in development (local.py creates the folder); production logs to stdout.

LOGS_DIR = BASE_DIR / "logs"

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
