from django.conf import settings

from apps.core.services.base import SmsBackend
from apps.core.services.bulksmsbd_sms_service import BulkSmsBdBackend
from apps.core.services.console_sms_service import ConsoleSmsBackend

BACKENDS = {
    'console': ConsoleSmsBackend,
    'bulksmsbd': BulkSmsBdBackend,
}


def get_sms_backend() -> SmsBackend:
    """Pick the SMS provider named by settings.SMS_BACKEND.

    An unknown name falls back to the console backend, so a typo in `.env`
    degrades to logging codes rather than breaking every signup.
    """
    name = str(getattr(settings, 'SMS_BACKEND', 'console') or '').strip().lower()
    return BACKENDS.get(name, ConsoleSmsBackend)()
