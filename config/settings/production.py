"""Production settings. Default for `wsgi.py` / `asgi.py`.

Set DJANGO_SETTINGS_MODULE=config.settings.production explicitly for
`manage.py` too when running migrations or collectstatic in a container --
otherwise manage.py falls back to the local module.
"""

from config.settings.base import *  # noqa: F403
from config.settings.base import env

DEBUG = False

# No default: a production boot with an unset ALLOWED_HOSTS should fail
# loudly rather than silently serve every Host header.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# Never blanket-allow cross-origin in production; base.py reads the
# CORS_ALLOWED_ORIGINS / CORS_ALLOWED_ORIGIN_REGEXES allowlists from env.
CORS_ALLOW_ALL_ORIGINS = False

# ---------------------------------------------------------------------------
# Transport security
#
# None of these existed before the settings split. They assume TLS is
# terminated at a proxy that sets X-Forwarded-Proto; set
# SECURE_SSL_REDIRECT=False if you terminate TLS elsewhere.
# ---------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Start low and raise once you are confident: HSTS is hard to undo because
# browsers cache the policy for its full duration.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
