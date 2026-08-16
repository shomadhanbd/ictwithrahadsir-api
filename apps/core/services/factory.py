from django.conf import settings

from apps.core.services.base import SmsBackend
from apps.core.services.console_sms_service import ConsoleSmsBackend

BACKENDS = {
    'console': ConsoleSmsBackend,
}


def get_sms_backend() -> SmsBackend:
    """Pick the SMS provider named by settings.SMS_BACKEND."""
    name = str(getattr(settings, 'SMS_BACKEND', 'console') or '').strip().lower()
    return BACKENDS.get(name, ConsoleSmsBackend)()
