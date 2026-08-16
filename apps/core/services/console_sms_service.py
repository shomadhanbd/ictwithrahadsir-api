from apps.core.services.base import SmsBackend
from apps.core.utils import get_logger

logger = get_logger('sms')


class ConsoleSmsBackend(SmsBackend):
    """Default backend: logs the message instead of sending real SMS, so the
    whole OTP flow works without a gateway account.

    Add a sibling `<vendor>_service.py` implementing `.send()` and register
    it in `factory.py` to switch to a real provider.
    """

    def send(self, phone: str, message: str) -> None:
        logger.info('[SMS to %s] %s', phone, message)
