"""Rate limits for the unauthenticated auth endpoints.

Nothing in the project was throttled, so `/api/login` accepted password
guesses as fast as they could be sent. The OTP endpoints have their own
per-phone protections (attempt cap and resend cooldown in `apps.identity`),
but those do nothing against an attacker working through passwords.

Two limits per endpoint rather than one: a burst limit stops the fast
scripted attack, and a sustained hourly limit stops the slow one that would
sit comfortably under any per-minute threshold.

These key on client IP, so keep the burst allowance loose enough for the
many real users who share one carrier NAT address.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginBurstThrottle(AnonRateThrottle):
    scope = 'login_burst'


class LoginSustainedThrottle(AnonRateThrottle):
    scope = 'login_sustained'


class AuthBurstThrottle(AnonRateThrottle):
    """For the account-creation and password-reset entry points."""

    scope = 'auth_burst'


class AuthSustainedThrottle(AnonRateThrottle):
    scope = 'auth_sustained'
