from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """Both frontends' axios interceptors send `Authorization: Bearer <token>`
    (not DRF's default `Token <token>`), matching how the old Laravel/Sanctum
    backend was addressed. Same token model/lookup as `TokenAuthentication`,
    just a different header keyword."""

    keyword = "Bearer"
