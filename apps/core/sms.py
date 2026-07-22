import logging

from django.conf import settings

logger = logging.getLogger("sms")


class SmsBackend:
    """Interface a real SMS gateway integration should implement."""

    def send(self, phone: str, message: str) -> None:
        raise NotImplementedError


class ConsoleSmsBackend(SmsBackend):
    """Default backend: logs the message instead of sending real SMS.

    Swap SMS_BACKEND in settings/.env for a real provider later by adding
    a class here (e.g. SslWirelessSmsBackend) that implements `.send()`.
    """

    def send(self, phone: str, message: str) -> None:
        logger.info("[SMS to %s] %s", phone, message)
        print(f"[SMS to {phone}] {message}")


def get_sms_backend() -> SmsBackend:
    backend_name = getattr(settings, "SMS_BACKEND", "console")
    backends = {
        "console": ConsoleSmsBackend,
    }
    backend_cls = backends.get(backend_name, ConsoleSmsBackend)
    return backend_cls()
