"""Every API error as `{message}`, plus `errors` for validation (422)."""

import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.api.auth.authentication import SessionExpired
from apps.core.exceptions import Conflict, ServiceUnavailable

logger = logging.getLogger("django.request")

NOT_FOUND = "Not found."
SERVER_ERROR = "Something went wrong."


def api_exception_handler(exc, context):
    response = _domain_error(exc)
    if response is not None:
        return response

    exc = _as_drf(exc)
    response = drf_exception_handler(exc, context)
    if response is None:
        return _unhandled(exc, context)

    response.data, response.status_code = _envelope(exc, response)
    return response


def _message(text, code):
    return Response({"message": text}, status=code)


def _domain_error(exc):
    """Errors DRF does not know, answered directly; None for anything else."""
    if isinstance(exc, Conflict):
        return _message(str(exc) or "This cannot be done in its current state.", status.HTTP_409_CONFLICT)
    if isinstance(exc, ProtectedError):  # checked before IntegrityError, which it extends
        return _message("This is still in use and cannot be deleted.", status.HTTP_409_CONFLICT)
    if isinstance(exc, ServiceUnavailable):  # the reason was logged where it failed
        return _message(exc.default_message, status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, IntegrityError):
        # Usually two requests racing for one unique value; logged in case it is a bug instead.
        logger.error("Integrity error answered as 409: %s", exc)
        return _message(
            "This conflicts with a record saved at the same moment. Please try again.", status.HTTP_409_CONFLICT
        )
    return None


def _as_drf(exc):
    """Business code raises Django's errors; DRF answers its own."""
    if isinstance(exc, DjangoValidationError):
        return exceptions.ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    if isinstance(exc, ObjectDoesNotExist):
        return exceptions.NotFound()
    return exc


def _unhandled(exc, context):
    """A bug: Django's debug page while developing, otherwise logged and answered as a 500."""
    if settings.DEBUG:
        return None
    logger.error("Unhandled error in %s", context["view"].__class__.__name__, exc_info=exc)
    return _message(SERVER_ERROR, status.HTTP_500_INTERNAL_SERVER_ERROR)


def _envelope(exc, response):
    """The body and status for an error DRF answered."""
    if isinstance(exc, exceptions.ValidationError):
        return _validation_body(exc.detail), status.HTTP_422_UNPROCESSABLE_ENTITY
    if response.status_code == status.HTTP_401_UNAUTHORIZED and not isinstance(exc, SessionExpired):
        return {"message": "Unauthenticated."}, response.status_code
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return {"message": NOT_FOUND}, response.status_code
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    return {"message": str(detail) if detail else SERVER_ERROR}, response.status_code


def _validation_body(detail):
    if isinstance(detail, dict):
        errors = {field: msgs if isinstance(msgs, list) else [msgs] for field, msgs in detail.items()}
        return {"message": "The given data was invalid.", "errors": errors}
    msgs = [str(m) for m in (detail if isinstance(detail, list) else [detail])]
    return {"message": " ".join(msgs), "errors": {"non_field_errors": msgs}}
