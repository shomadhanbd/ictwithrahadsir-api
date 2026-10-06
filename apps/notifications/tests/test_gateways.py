"""The SMS gateways and the setting that picks one."""

from unittest import mock

from django.test import TestCase, override_settings

import requests

from apps.notifications.gateways import BulkSmsBdBackend, ConsoleSmsBackend, SmsError, get_gateway

ACCEPTED = BulkSmsBdBackend.ACCEPTED


def fake_response(payload, status=200):
    response = mock.Mock()
    response.json.return_value = payload
    response.status_code = status
    response.raise_for_status.return_value = None
    return response


class SmsBackendFactoryTests(TestCase):
    @override_settings(SMS_BACKEND='bulksmsbd')
    def test_it_resolves_the_named_provider(self):
        self.assertIsInstance(get_gateway(), BulkSmsBdBackend)

    @override_settings(SMS_BACKEND='console')
    def test_console_is_the_default(self):
        self.assertIsInstance(get_gateway(), ConsoleSmsBackend)

    @override_settings(SMS_BACKEND='no-such-gateway')
    def test_an_unknown_name_falls_back_rather_than_raising(self):
        """A typo in `.env` must degrade to logging, not break every signup."""
        self.assertIsInstance(get_gateway(), ConsoleSmsBackend)


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
        """A 200 with BulkSMSBD's error code 1002 counts as a failed send."""
        with (
            mock.patch('requests.post', return_value=fake_response({'response_code': 1002})),
            self.assertRaises(SmsError),
        ):
            BulkSmsBdBackend().send('01711111111', 'code 123456')

    def test_every_failure_is_an_sms_error(self):
        """Callers catch one exception whatever went wrong."""
        failures = {
            'connection': {'side_effect': requests.ConnectionError('down')},
            'timeout': {'side_effect': requests.Timeout('slow')},
            'http error': {
                'return_value': mock.Mock(raise_for_status=mock.Mock(side_effect=requests.HTTPError('500')))
            },
            'junk body': {
                'return_value': mock.Mock(raise_for_status=mock.Mock(), json=mock.Mock(side_effect=ValueError))
            },
        }
        for name, patched in failures.items():
            with self.subTest(name), mock.patch('requests.post', **patched), self.assertRaises(SmsError):
                BulkSmsBdBackend().send('01711111111', 'code 123456')

    def test_a_string_success_code_counts_as_accepted(self):
        self.send({'response_code': str(ACCEPTED)})


@override_settings(BULKSMSBD_API_KEY='key-123')
class BulkSmsBdBalanceTests(TestCase):
    def test_it_reports_whole_taka(self):
        with mock.patch('requests.get', return_value=fake_response({'balance': '1234.56'})):
            self.assertEqual(BulkSmsBdBackend().balance(), {'balance': 1234, 'currency': 'BDT'})

    def test_a_failed_lookup_is_unavailable_rather_than_zero(self):
        """Zero would read as "out of credit"; None tells the panel the lookup failed."""
        with mock.patch('requests.get', side_effect=requests.Timeout('slow')):
            self.assertEqual(BulkSmsBdBackend().balance(), {'balance': None, 'currency': 'BDT'})

    def test_a_junk_body_is_unavailable(self):
        with mock.patch('requests.get', return_value=fake_response({'balance': 'not-a-number'})):
            self.assertIsNone(BulkSmsBdBackend().balance()['balance'])

    def test_the_console_backend_has_no_balance(self):
        self.assertEqual(ConsoleSmsBackend().balance(), {'balance': None, 'currency': 'BDT'})


class GatewayLogTests(TestCase):
    def test_the_sms_gateway_log_carries_no_full_number(self):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {'response_code': 202}
        with (
            mock.patch('apps.notifications.gateways.requests.post', return_value=reply),
            self.assertLogs('sms', level='INFO') as logs,
        ):
            BulkSmsBdBackend().send('01810001111', 'code 123456')
        self.assertNotIn('01810001111', '\n'.join(logs.output))
