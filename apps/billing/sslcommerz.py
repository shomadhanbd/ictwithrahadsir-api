"""SSLCommerz, the only payment gateway.

Two calls: open a payment session (the student is redirected to the page it
returns), and validate a payment SSLCommerz has reported. A callback's own
POSTed fields are never trusted -- only what the validation API says.

`settings.SSLCOMMERZ_SANDBOX` picks the sandbox or the live host. Never log the
store password or a full request.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.urls import reverse

import requests

logger = logging.getLogger('payments')

SANDBOX_URL = 'https://sandbox.sslcommerz.com'
LIVE_URL = 'https://securepay.sslcommerz.com'
SESSION_PATH = '/gwprocess/v4/api.php'
VALIDATION_PATH = '/validator/api/validationserverAPI.php'
TIMEOUT_SECONDS = 15

#: What SSLCommerz accepts for one transaction, in BDT.
MIN_AMOUNT = Decimal('10')
MAX_AMOUNT = Decimal('500000')

#: Validation statuses that mean the money was taken. `VALIDATED` is a repeat
#: validation of one already `VALID`.
PAID_STATUSES = {'VALID', 'VALIDATED'}


class SslCommerzError(RuntimeError):
    """SSLCommerz could not be reached, or refused the request."""


def is_configured() -> bool:
    return bool(settings.SSLCOMMERZ_STORE_ID and settings.SSLCOMMERZ_STORE_PASSWORD)


def base_url() -> str:
    return SANDBOX_URL if settings.SSLCOMMERZ_SANDBOX else LIVE_URL


def callback_urls() -> dict:
    """Where SSLCommerz sends the student's browser, and its own IPN."""
    origin = settings.API_BASE_URL.rstrip('/')
    return {
        f'{name}_url': origin + reverse(f'api:billing:sslcommerz_{name}')
        for name in ('success', 'fail', 'cancel', 'ipn')
    }


def create_session(*, tran_id, amount, customer: dict, product_name, product_category) -> str:
    """Open a payment session and return the gateway page to send the student to."""
    data = {
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
        'total_amount': f'{amount:.2f}',
        'currency': 'BDT',
        'tran_id': tran_id,
        **callback_urls(),
        'cus_name': customer['name'],
        'cus_email': customer['email'],
        'cus_phone': customer['phone'],
        'cus_add1': customer.get('address') or 'N/A',
        'cus_city': 'Dhaka',
        'cus_postcode': '1000',
        'cus_country': 'Bangladesh',
        'shipping_method': 'NO',
        'num_of_item': 1,
        'product_name': product_name[:255],
        'product_category': product_category,
        'product_profile': 'non-physical-goods',
    }
    try:
        response = requests.post(base_url() + SESSION_PATH, data=data, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error('SSLCommerz session for %s failed: %s', tran_id, exc)
        raise SslCommerzError('Could not reach SSLCommerz.') from exc

    if body.get('status') != 'SUCCESS' or not body.get('GatewayPageURL'):
        reason = body.get('failedreason') or 'unknown reason'
        logger.error('SSLCommerz refused the session for %s: %s', tran_id, reason)
        raise SslCommerzError(f'SSLCommerz refused the payment: {reason}')
    return body['GatewayPageURL']


def validate(val_id) -> dict:
    """What SSLCommerz says about a reported payment -- the only thing trusted."""
    params = {
        'val_id': val_id,
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
        'v': 1,
        'format': 'json',
    }
    try:
        response = requests.get(base_url() + VALIDATION_PATH, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error('SSLCommerz validation of %s failed: %s', val_id, exc)
        raise SslCommerzError('Could not reach SSLCommerz.') from exc

    logger.info('SSLCommerz validated %s for %s: %s', val_id, body.get('tran_id'), body.get('status'))
    return body
