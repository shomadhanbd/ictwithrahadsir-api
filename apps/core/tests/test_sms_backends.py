"""The SMS gateway adapters and the factory that chooses between them.

Nothing here touches the network: `requests` is patched at every call site,
which is also the guard that this suite can never spend real SMS credit.
"""

from unittest import mock

from django.test import TestCase, override_settings

import requests

from apps.core.services.bulksmsbd_sms_service import (
    ACCEPTED,
    BulkSmsBdBackend,
    BulkSmsBdError,
)
from apps.core.services.console_sms_service import ConsoleSmsBackend
from apps.core.services.factory import get_sms_backend


def fake_response(payload, status=200):
    response = mock.Mock()
    response.json.return_value = payload
    response.status_code = status
    response.raise_for_status.return_value = None
    return response


class SmsBackendFactoryTests(TestCase):
    @override_settings(SMS_BACKEND='bulksmsbd')
    def test_it_resolves_the_named_provider(self):
        self.assertIsInstance(get_sms_backend(), BulkSmsBdBackend)

    @override_settings(SMS_BACKEND='console')
    def test_console_is_the_default(self):
        self.assertIsInstance(get_sms_backend(), ConsoleSmsBackend)

    @override_settings(SMS_BACKEND='no-such-gateway')
    def test_an_unknown_name_falls_back_rather_than_raising(self):
        """A typo in `.env` must degrade to logging, not break every signup."""
        self.assertIsInstance(get_sms_backend(), ConsoleSmsBackend)


class GatewayNumberTests(TestCase):
    """`normalize_phone` stores the local `01...` form; the gateway wants
    the country code back on."""

    def test_a_local_number_gains_the_country_code(self):
        self.assertEqual(BulkSmsBdBackend.gateway_number('01711111111'), '8801711111111')

    def test_an_already_prefixed_number_is_left_alone(self):
        self.assertEqual(BulkSmsBdBackend.gateway_number('8801711111111'), '8801711111111')

    def test_punctuation_is_stripped(self):
        self.assertEqual(BulkSmsBdBackend.gateway_number('+880 171-111 1111'), '8801711111111')


@override_settings(BULKSMSBD_API_KEY='key-123', BULKSMSBD_SENDER_ID='SHOMADHAN')
class BulkSmsBdSendTests(TestCase):
    def send(self, payload, **kwargs):
        with mock.patch('requests.post', return_value=fake_response(payload)) as post:
            BulkSmsBdBackend().send(kwargs.pop('phone', '01711111111'), 'code 123456')
        return post

    def test_a_successful_send_posts_the_expected_payload(self):
        post = self.send({'response_code': ACCEPTED})

        _, called = post.call_args
        self.assertEqual(called['data']['api_key'], 'key-123')
        self.assertEqual(called['data']['senderid'], 'SHOMADHAN')
        self.assertEqual(called['data']['type'], 'text')
        self.assertEqual(called['data']['number'], '8801711111111')
        self.assertEqual(called['data']['message'], 'code 123456')

    def test_the_request_carries_a_timeout(self):
        """Without one, a hung gateway holds a gunicorn worker open."""
        post = self.send({'response_code': ACCEPTED})
        self.assertEqual(post.call_args.kwargs['timeout'], 10)

    def test_a_refusal_raises_even_though_the_http_status_was_200(self):
        """BulkSMSBD reports a bad API key as 200 + response_code 1002. Left
        unchecked, a misconfigured key looks like a successful send forever."""
        with (
            mock.patch('requests.post', return_value=fake_response({'response_code': 1002})),
            self.assertRaises(BulkSmsBdError),
        ):
            BulkSmsBdBackend().send('01711111111', 'code 123456')

    def test_a_transport_failure_propagates(self):
        with (
            mock.patch('requests.post', side_effect=requests.ConnectionError('down')),
            self.assertRaises(requests.ConnectionError),
        ):
            BulkSmsBdBackend().send('01711111111', 'code 123456')


@override_settings(BULKSMSBD_API_KEY='key-123')
class BulkSmsBdBalanceTests(TestCase):
    def test_it_reports_whole_taka(self):
        with mock.patch('requests.get', return_value=fake_response({'balance': '1234.56'})):
            self.assertEqual(BulkSmsBdBackend().balance(), {'balance': 1234, 'currency': 'BDT'})

    def test_a_failed_lookup_reports_zero_rather_than_raising(self):
        """A dead balance call must not take the admin dashboard down with
        it -- unlike a send, nobody is waiting on it to log in."""
        with mock.patch('requests.get', side_effect=requests.Timeout('slow')):
            self.assertEqual(BulkSmsBdBackend().balance(), {'balance': 0, 'currency': 'BDT'})

    def test_a_junk_body_reports_zero(self):
        with mock.patch('requests.get', return_value=fake_response({'balance': 'not-a-number'})):
            self.assertEqual(BulkSmsBdBackend().balance()['balance'], 0)

    def test_the_console_backend_reports_zero(self):
        self.assertEqual(ConsoleSmsBackend().balance(), {'balance': 0, 'currency': 'BDT'})
