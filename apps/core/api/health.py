"""A probe for load balancers and uptime checks: is the app up, and can it reach its database and cache?"""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

HEALTH_PATH = "/api/health/"


class HealthCheckMiddleware:
    """Answers the probe before any other middleware, so a load balancer probing by IP (a Host header not in
    ALLOWED_HOSTS) over plain http is neither redirected to https nor refused as a bad host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != HEALTH_PATH or request.method not in ("GET", "HEAD"):
            return self.get_response(request)
        checks = {"database": _database_ok(), "cache": _cache_ok()}
        healthy = all(checks.values())
        return JsonResponse({"ok": healthy, **checks}, status=200 if healthy else 503)


def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


def _cache_ok() -> bool:
    try:
        cache.set("health-check", "ok", timeout=5)
        return cache.get("health-check") == "ok"
    except Exception:
        return False
