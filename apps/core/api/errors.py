"""Django's own 404 and 500 pages, as the JSON envelope under /api/ (DRF views never reach these)."""

from django.http import JsonResponse
from django.views.defaults import page_not_found, server_error


def _is_api(request) -> bool:
    return request.path.startswith("/api/")


def not_found(request, exception):
    if _is_api(request):
        return JsonResponse({"message": "Not found."}, status=404)
    return page_not_found(request, exception)


def server_failure(request):
    if _is_api(request):
        return JsonResponse({"message": "Something went wrong."}, status=500)
    return server_error(request)
