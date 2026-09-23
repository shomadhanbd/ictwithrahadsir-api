from django.db.models import ProtectedError

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def laravel_style_exception_handler(exc, context):
    """Render errors in the envelope both frontends parse:
    `{message, errors: {field: [msg, ...]}}` for validation errors,
    `{message}` for everything else."""
    if isinstance(exc, ProtectedError):
        # Deleting a row a `PROTECT` foreign key still points at.
        return Response(
            {"message": "This is still in use and cannot be deleted."},
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

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
            response.data = {"message": " ".join(str(m) for m in messages)}
    elif isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        response.data = {"message": "Unauthenticated."}
    elif isinstance(exc, exceptions.PermissionDenied):
        response.data = {"message": str(exc.detail)}
    elif isinstance(exc, exceptions.NotFound):
        response.data = {"message": "Not found."}
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        response.data = {"message": str(detail) if detail else "Something went wrong."}
    return response
