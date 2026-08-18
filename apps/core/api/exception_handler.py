from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler


def laravel_style_exception_handler(exc, context):
    """
    Normalizes DRF exceptions into the Laravel-style error envelope both
    frontends already parse: `{message, errors: {field: [msg, ...]}}` for
    validation errors, `{message}` for everything else.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        if isinstance(detail, dict):
            errors = {
                field: messages if isinstance(messages, list) else [messages]
                for field, messages in detail.items()
            }
            response.data = {"message": "The given data was invalid.", "errors": errors}
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        else:
            messages = detail if isinstance(detail, list) else [detail]
            response.data = {"message": " ".join(str(m) for m in messages)}
        return response

    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        response.data = {"message": "Unauthenticated."}
        return response

    if isinstance(exc, exceptions.PermissionDenied):
        response.data = {"message": str(exc.detail) if hasattr(exc, "detail") else "Forbidden."}
        return response

    if isinstance(exc, exceptions.NotFound):
        response.data = {"message": "Not found."}
        return response

    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    response.data = {"message": str(detail) if detail else "Something went wrong."}
    return response
