from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """DRF token auth read from `Authorization: Bearer <token>`, the header
    both frontends send."""

    keyword = "Bearer"


class BearerTokenScheme(OpenApiAuthenticationExtension):
    """Names the scheme `bearerTokenAuth` in the OpenAPI schema."""

    target_class = 'apps.core.api.authentication.BearerTokenAuthentication'
    name = 'bearerTokenAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Token-based authentication with the required prefix "Bearer".',
        }
