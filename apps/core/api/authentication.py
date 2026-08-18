from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """Both frontends' axios interceptors send `Authorization: Bearer <token>`
    (not DRF's default `Token <token>`), matching how the old Laravel/Sanctum
    backend was addressed. Same token model/lookup as `TokenAuthentication`,
    just a different header keyword."""

    keyword = "Bearer"


class BearerTokenScheme(OpenApiAuthenticationExtension):
    """Names `BearerTokenAuthentication` distinctly in the OpenAPI schema.

    Both it and DRF's own `TokenAuthentication` are enabled, and both would
    otherwise be emitted as a component called `tokenAuth` -- two different
    schemes under one name, which drf-spectacular warns produces an incorrect
    document. They differ only in the header keyword, so both are described,
    separately and accurately.
    """

    target_class = 'apps.core.api.authentication.BearerTokenAuthentication'
    name = 'bearerTokenAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Token-based authentication with the required prefix "Bearer".',
        }
