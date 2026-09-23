"""Rate limits for the unauthenticated auth endpoints, keyed on client IP.

Each endpoint gets a burst limit (fast scripted attacks) and a sustained
hourly one (slow attacks). Rates are set in `REST_FRAMEWORK` settings.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginBurstThrottle(AnonRateThrottle):
    scope = 'login_burst'


class LoginSustainedThrottle(AnonRateThrottle):
    scope = 'login_sustained'


class AuthBurstThrottle(AnonRateThrottle):
    """Registration and password reset."""

    scope = 'auth_burst'


class AuthSustainedThrottle(AnonRateThrottle):
    scope = 'auth_sustained'
