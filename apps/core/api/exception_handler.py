import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.api.authentication import SessionExpired
from apps.core.api.exceptions import Conflict as ConflictResponse
from apps.core.exceptions import Conflict

logger = logging.getLogger("django.request")


def _as_drf(exc):
    """Domain code raises Django's errors; answer them like DRF's own."""
    if isinstance(exc, DjangoValidationError):
        return exceptions.ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    if isinstance(exc, ObjectDoesNotExist):
        return exceptions.NotFound()
    if isinstance(exc, Conflict):
        return ConflictResponse(str(exc) or None)
    return exc


def laravel_style_exception_handler(exc, context):
    """Renders `{message, errors}` for validation errors and `{message}` otherwise."""
    if isinstance(exc, ProtectedError):
        return Response(
            {"message": "This is still in use and cannot be deleted."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        # Two requests racing for the same unique value: the loser is told, not shown a 500.
        logger.warning("Integrity error answered as 409: %s", exc)
        return Response(
            {"message": "This conflicts with a record saved at the same moment. Please try again."},
            status=status.HTTP_409_CONFLICT,
        )

    exc = _as_drf(exc)
    response = drf_exception_handler(exc, context)
    if response is None:
        if settings.DEBUG:
            return None  # Django's debug page
        # Logged here because answering it stops Django from logging it; the client still gets the envelope.
        logger.error("Unhandled error in %s", context["view"].__class__.__name__, exc_info=exc)
        return Response({"message": "Something went wrong."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        if isinstance(detail, dict):
            errors = {
                field: messages if isinstance(messages, list) else [messages] for field, messages in detail.items()
            }
            response.data = {"message": "The given data was invalid.", "errors": errors}
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        else:
            messages = detail if isinstance(detail, list) else [detail]
            response.data = {
                "message": " ".join(str(m) for m in messages),
                "errors": {"non_field_errors": [str(m) for m in messages]},
            }
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, exceptions.NotAuthenticated):
        response.data = {"message": "Unauthenticated."}
    elif isinstance(exc, SessionExpired):
        response.data = {"message": str(exc.detail)}
    elif isinstance(exc, exceptions.AuthenticationFailed):
        response.data = {"message": "Unauthenticated."}
    elif isinstance(exc, exceptions.PermissionDenied):
        response.data = {"message": str(exc.detail)}
    elif isinstance(exc, exceptions.NotFound):
        response.data = {"message": "Not found."}
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        response.data = {"message": str(detail) if detail else "Something went wrong."}
    return response
