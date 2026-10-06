"""Django's 404 and 500 handlers: JSON under /api/ (for errors that never reach a DRF view), HTML elsewhere."""

from django.http import JsonResponse
from django.views.defaults import page_not_found, server_error

from apps.core.api.errors.handler import NOT_FOUND, SERVER_ERROR


def not_found(request, exception):
    if _is_api(request):
        return JsonResponse({"message": NOT_FOUND}, status=404)
    return page_not_found(request, exception)


def server_failure(request):
    if _is_api(request):
        return JsonResponse({"message": SERVER_ERROR}, status=500)
    return server_error(request)


def _is_api(request) -> bool:
    return request.path.startswith("/api/")
