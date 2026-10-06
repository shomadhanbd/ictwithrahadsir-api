"""Shared billing fixtures.

SSLCommerz is never contacted: the session and Validator API calls are patched,
while callbacks are signed for real. Access is granted on commit, so captures run
inside `captureOnCommitCallbacks(execute=True)`.
"""

import hashlib
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.urls import reverse

from rest_framework.test import APITestCase
from sslcommerz_lib import SSLCOMMERZ

from apps.billing.models import Payment, Product
from apps.core.testing import bearer, make_user
from apps.courses.models import Course, Enrollment

STORE_PASSWORD = 'secret'
GATEWAY_PAGE = 'https://sandbox.sslcommerz.com/EasyCheckOut/abc'
SUCCESS = 'https://site.test/payment/success'
FAIL = 'https://site.test/payment/fail'
CANCEL = 'https://site.test/payment/cancel'

GATEWAY = override_settings(
    SSLCOMMERZ_STORE_ID='store',
    SSLCOMMERZ_STORE_PASSWORD=STORE_PASSWORD,
    SSLCOMMERZ_IS_SANDBOX=True,
    API_BASE_URL='https://api.test',
    SSLCOMMERZ_SUCCESS_REDIRECT=SUCCESS,
    SSLCOMMERZ_FAIL_REDIRECT=FAIL,
    SSLCOMMERZ_CANCEL_REDIRECT=CANCEL,
)

INITIATE_URL = reverse('api:billing:payment_initiate')
CAPTURE_URL = reverse('api:billing:payment_capture')
IPN_URL = reverse('api:billing:payment_ipn')
MY_PAYMENTS_URL = reverse('api:billing:my_payments')


def session_ok():
    return patch.object(SSLCOMMERZ, 'createSession', return_value={'status': 'SUCCESS', 'GatewayPageURL': GATEWAY_PAGE})


def validator(payment, **overrides):
    """What SSLCommerz's Validator API says about `payment`."""
    body = {
        'status': 'VALID',
        'tran_id': payment.transaction_id,
        'amount': f'{payment.amount}.00',
        'value_a': str(payment.user_id),
        **overrides,
    }
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return patch('apps.billing.services.sslcommerz.http_requests.get', return_value=response)


def signed(**data):
    """A callback body signed as SSLCommerz signs it."""
    params = {**data, 'store_passwd': hashlib.md5(STORE_PASSWORD.encode()).hexdigest()}
    hash_string = '&'.join(f'{key}={value}' for key, value in sorted(params.items()))
    return {**data, 'verify_key': ','.join(data), 'verify_sign': hashlib.md5(hash_string.encode()).hexdigest()}


@GATEWAY
class BillingTestBase(APITestCase):
    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        # A bundle: one live course and one recorded, for a year.
        self.live = Course.objects.create(title='ICT Live Batch', slug='ict-live', status='published', is_online=True)
        self.recorded = Course.objects.create(title='ICT Recorded', slug='ict-rec', status='published', is_online=False)
        self.product = Product.objects.create(
            title='HSC ICT Package', product_id='hsc-ict', price=500, base_price=600, access_days=365
        )
        self.product.courses.set([self.live, self.recorded])
        self.course = Course.objects.create(title='ICT', slug='ict', status='published')

    def initiate(self, auth=None, **body):
        with session_ok() as create_session:
            response = self.client.post(INITIATE_URL, body, format='json', **(auth or self.auth))
        return response, create_session

    def started(self, **body):
        response, _ = self.initiate(**body or {'product_id': 'hsc-ict'})
        self.assertEqual(response.status_code, 201, response.content)
        return Payment.objects.get(transaction_id=response.json()['transaction_id'])

    def capture(self, payment, status='VALID', **overrides):
        """SSLCommerz redirecting the student's browser back."""
        with validator(payment, **overrides), self.captureOnCommitCallbacks(execute=True):
            return self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, val_id='VAL-1', status=status))

    def enrolment(self, course):
        return Enrollment.objects.get(user=self.student, course=course)
