"""Rate limits; the rates live in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`."""

from rest_framework.throttling import SimpleRateThrottle


class ClientIpRateThrottle(SimpleRateThrottle):
    """Per client IP, signed in or not, so a token of one's own buys no extra guesses."""

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class LoginBurstThrottle(ClientIpRateThrottle):
    scope = 'login_burst'


class LoginSustainedThrottle(ClientIpRateThrottle):
    scope = 'login_sustained'


class AuthBurstThrottle(ClientIpRateThrottle):
    """Registration and password reset."""

    scope = 'auth_burst'


class AuthSustainedThrottle(ClientIpRateThrottle):
    scope = 'auth_sustained'


class PracticeThrottle(SimpleRateThrottle):
    """Free practice: per user when signed in, else per IP."""

    scope = 'practice'

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
