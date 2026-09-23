"""SMS delivery. `settings.SMS_BACKEND` picks the provider: "console" (default,
logs the message) or "bulksmsbd"."""

import logging

from django.conf import settings

import requests

logger = logging.getLogger('sms')


class SmsBackend:
    def send(self, phone: str, message: str) -> None:
        raise NotImplementedError

    def balance(self) -> dict:
        return {'balance': 0, 'currency': 'BDT'}


class ConsoleSmsBackend(SmsBackend):
    """Logs the message instead of sending it, for development."""

    def send(self, phone: str, message: str) -> None:
        logger.info('[SMS to %s] %s', phone, message)


class BulkSmsBdError(RuntimeError):
    """The gateway accepted the request but refused the message."""


class BulkSmsBdBackend(SmsBackend):
    SEND_URL = 'https://bulksmsbd.net/api/smsapi'
    BALANCE_URL = 'https://bulksmsbd.net/api/getBalanceApi'
    # Refusals (bad key, no credit, ...) also arrive as HTTP 200, so success is
    # this `response_code`, not the status.
    ACCEPTED = 202
    TIMEOUT_SECONDS = 10

    def send(self, phone: str, message: str) -> None:
        payload = {
            'api_key': settings.BULKSMSBD_API_KEY,
            'senderid': settings.BULKSMSBD_SENDER_ID,
            'type': 'text',
            'number': self.gateway_number(phone),
            'message': message,
        }
        response = requests.post(self.SEND_URL, data=payload, timeout=self.TIMEOUT_SECONDS)
        response.raise_for_status()

        try:
            code = response.json().get('response_code')
        except ValueError:
            code = None
        if code != self.ACCEPTED:
            # Never log `message`: it carries the OTP.
            logger.error('BulkSMSBD refused the message to %s (response_code=%s)', phone, code)
            raise BulkSmsBdError(f'BulkSMSBD returned response_code {code}.')

        logger.info('BulkSMSBD accepted a message for %s', phone)

    def balance(self) -> dict:
        """Remaining credit in whole taka, or zero if the lookup fails."""
        try:
            response = requests.get(
                self.BALANCE_URL,
                params={'api_key': settings.BULKSMSBD_API_KEY},
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return {'balance': int(float(response.json().get('balance') or 0)), 'currency': 'BDT'}
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning('BulkSMSBD balance lookup failed: %s', exc)
            return {'balance': 0, 'currency': 'BDT'}

    @staticmethod
    def gateway_number(phone: str) -> str:
        """Stored `01XXXXXXXXX` -> the `8801XXXXXXXXX` the gateway expects."""
        digits = ''.join(filter(str.isdigit, phone or ''))
        if digits.startswith('880'):
            return digits
        return f'880{digits.lstrip("0")}'


BACKENDS = {
    'console': ConsoleSmsBackend,
    'bulksmsbd': BulkSmsBdBackend,
}


def get_sms_backend() -> SmsBackend:
    """The configured backend; an unknown name falls back to the console one."""
    name = str(getattr(settings, 'SMS_BACKEND', 'console') or '').strip().lower()
    return BACKENDS.get(name, ConsoleSmsBackend)()
