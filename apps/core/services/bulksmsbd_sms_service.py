"""BulkSMSBD gateway integration.

The only file in the project that names an SMS vendor. Everything above it
calls `SmsBackend.send()` and never learns which provider answered, which is
what makes swapping gateways a one-file change.
"""

from django.conf import settings

import requests

from apps.core.services.base import SmsBackend
from apps.core.utils import get_logger

logger = get_logger('sms')

SEND_URL = 'https://bulksmsbd.net/api/smsapi'
BALANCE_URL = 'https://bulksmsbd.net/api/getBalanceApi'

#: The one `response_code` BulkSMSBD returns for an accepted message. Every
#: other value (1001-1032: bad API key, no balance, invalid sender ID, ...)
#: arrives with HTTP 200, so `raise_for_status()` alone would let a wrong
#: API key look like a successful send forever.
ACCEPTED = 202

#: A hung gateway must not hold a gunicorn worker open indefinitely.
TIMEOUT_SECONDS = 10


class BulkSmsBdError(RuntimeError):
    """The gateway accepted the request but refused the message."""


class BulkSmsBdBackend(SmsBackend):
    """Sends through bulksmsbd.net.

    Delivery failures are raised rather than swallowed: an OTP the user is
    waiting for is worth a 500 they can retry, not a silent success that
    leaves them staring at an empty inbox.
    """

    def send(self, phone: str, message: str) -> None:
        payload = {
            'api_key': settings.BULKSMSBD_API_KEY,
            'senderid': settings.BULKSMSBD_SENDER_ID,
            'type': 'text',
            'number': self.gateway_number(phone),
            'message': message,
        }
        response = requests.post(SEND_URL, data=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()

        code = self._response_code(response)
        if code != ACCEPTED:
            # Never log `message` -- it carries the OTP.
            logger.error('BulkSMSBD refused the message to %s (response_code=%s)', phone, code)
            raise BulkSmsBdError(f'BulkSMSBD returned response_code {code}.')

        logger.info('BulkSMSBD accepted a message for %s', phone)

    def balance(self) -> dict:
        """Remaining credit, or zero when the lookup fails.

        A dead balance lookup must not take the admin dashboard down with it
        -- unlike `send`, nobody is waiting on this number to log in.
        """
        try:
            response = requests.get(
                BALANCE_URL,
                params={'api_key': settings.BULKSMSBD_API_KEY},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json()
            # `balance` comes back as a decimal string ("1234.56"). The admin
            # readout is an integer field, and whole taka is precise enough
            # for "do we have credit left?".
            return {'balance': int(float(body.get('balance') or 0)), 'currency': 'BDT'}
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning('BulkSMSBD balance lookup failed: %s', exc)
            return {'balance': 0, 'currency': 'BDT'}

    @staticmethod
    def gateway_number(phone: str) -> str:
        """Local `01XXXXXXXXX` -> the `8801XXXXXXXXX` the gateway expects.

        `apps.core.phones.normalize_phone` deliberately stores the local
        form, so the country code is re-attached here and nowhere else.
        """
        digits = ''.join(filter(str.isdigit, phone or ''))
        if digits.startswith('880'):
            return digits
        return f'880{digits.lstrip("0")}'

    @staticmethod
    def _response_code(response):
        """`response_code` from the JSON body, or None if it isn't JSON."""
        try:
            return response.json().get('response_code')
        except ValueError:
            return None
