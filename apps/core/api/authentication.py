from django.conf import settings
from django.utils import timezone

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class SessionExpired(AuthenticationFailed):
    """A token past TOKEN_TTL_DAYS; the one 401 whose reason is worth telling the user."""

    default_detail = "Your session has expired. Please sign in again."


def token_expired(token) -> bool:
    return timezone.now() - token.created > timezone.timedelta(days=settings.TOKEN_TTL_DAYS)


class BearerTokenAuthentication(TokenAuthentication):
    """DRF token auth read from the `Authorization: Bearer <token>` header both frontends send."""

    keyword = "Bearer"

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token_expired(token):
            raise SessionExpired()
        return user, token
