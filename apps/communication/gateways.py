"""SMS gateways, chosen by `settings.SMS_BACKEND`. Send through `services.send_sms`, never directly."""

import logging

from django.conf import settings

import requests

from apps.core.exceptions import ServiceUnavailable
from apps.core.text.phones import masked_phone

logger = logging.getLogger("sms")


class SmsError(ServiceUnavailable):
    """The message did not reach the gateway; the API answers 503."""

    default_message = "We couldn't send the SMS. Please try again shortly."


class ConsoleSmsBackend:
    """Logs the message instead of sending it (development)."""

    def send(self, phone: str, message: str) -> None:
        logger.info("[SMS to %s] %s", phone, message)

    def balance(self) -> dict:
        return {"balance": None, "currency": "BDT"}


class BulkSmsBdBackend:
    SEND_URL = "https://bulksmsbd.net/api/smsapi"
    BALANCE_URL = "https://bulksmsbd.net/api/getBalanceApi"
    ACCEPTED = 202  # refusals also arrive as HTTP 200, so this code is what marks success
    TIMEOUT_SECONDS = 10

    def send(self, phone: str, message: str) -> None:
        payload = {
            "api_key": settings.BULKSMSBD_API_KEY,
            "senderid": settings.BULKSMSBD_SENDER_ID,
            "type": "text",
            "number": f"88{phone}",  # 01XXXXXXXXX -> 8801XXXXXXXXX
            "message": message,
        }
        try:
            response = requests.post(self.SEND_URL, data=payload, timeout=self.TIMEOUT_SECONDS)
            response.raise_for_status()
            code = response.json().get("response_code")
        except (requests.RequestException, ValueError) as exc:
            logger.error("BulkSMSBD send to %s failed: %s", masked_phone(phone), exc)
            raise SmsError("The SMS gateway could not be reached.") from exc

        # Never log the message: it can carry an OTP.
        if str(code) != str(self.ACCEPTED):
            logger.error("BulkSMSBD refused the message to %s (response_code=%s)", masked_phone(phone), code)
            raise SmsError(f"BulkSMSBD returned response_code {code}.")
        logger.info("BulkSMSBD accepted a message for %s", masked_phone(phone))

    def balance(self) -> dict:
        """Credit in whole taka; None if the lookup fails (not zero, which would read as "out of credit")."""
        try:
            response = requests.get(
                self.BALANCE_URL, params={"api_key": settings.BULKSMSBD_API_KEY}, timeout=self.TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return {"balance": int(float(response.json()["balance"])), "currency": "BDT"}
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            logger.warning("BulkSMSBD balance lookup failed: %s", exc)
            return {"balance": None, "currency": "BDT"}


BACKENDS = {"console": ConsoleSmsBackend, "bulksmsbd": BulkSmsBdBackend}


def get_gateway():
    """The configured gateway; an unknown name falls back to the console."""
    return BACKENDS.get(settings.SMS_BACKEND, ConsoleSmsBackend)()
