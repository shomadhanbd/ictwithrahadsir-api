"""Every SMS goes through `send_sms`, which records it; OTP codes are never stored."""

from unittest import mock

from django.test import TestCase

from apps.communication.gateways import SmsError
from apps.communication.models import SmsMessage
from apps.communication.services import send_sms
from apps.core.testing import make_user

GATEWAY = 'apps.communication.services.get_gateway'


class SendSmsTests(TestCase):
    def test_a_sent_message_is_recorded(self):
        student = make_user()
        with mock.patch(GATEWAY) as gateway:
            record = send_sms(
                '01810001111', 'Your access ends soon.', purpose=SmsMessage.Purpose.EXPIRY_REMINDER, recipient=student
            )

        gateway.return_value.send.assert_called_once_with('01810001111', 'Your access ends soon.')
        record.refresh_from_db()
        self.assertEqual(
            (record.status, record.body, record.recipient, record.sent_by),
            (SmsMessage.Status.SENT, 'Your access ends soon.', student, None),
        )

    def test_a_failure_is_recorded_then_raised(self):
        with mock.patch(GATEWAY) as gateway, self.assertRaises(SmsError):
            gateway.return_value.send.side_effect = SmsError('gateway down')
            send_sms('01810001111', 'Hello', purpose=SmsMessage.Purpose.CUSTOM)

        record = SmsMessage.objects.get()
        self.assertEqual((record.status, record.error), (SmsMessage.Status.FAILED, 'gateway down'))

    def test_an_otp_code_is_never_stored(self):
        for purpose in SmsMessage.SECRET_PURPOSES:
            with self.subTest(purpose=purpose), mock.patch(GATEWAY) as gateway:
                record = send_sms('01810001111', 'Your code is 123456', purpose=purpose)
                gateway.return_value.send.assert_called_once_with('01810001111', 'Your code is 123456')
                self.assertEqual(record.body, '')

    def test_who_sent_it_is_kept(self):
        admin = make_user()
        with mock.patch(GATEWAY):
            record = send_sms('01810001111', 'Fees are due.', purpose=SmsMessage.Purpose.GUARDIAN, sent_by=admin)
        self.assertEqual(record.sent_by, admin)


class CallerTests(TestCase):
    def test_requesting_an_otp_records_a_phone_verification(self):
        with mock.patch(GATEWAY):
            self.client.get('/api/public/auth/otp/', {'phone': '01810001111'})
        self.assertEqual(
            list(SmsMessage.objects.values_list('purpose', 'body', 'status')),
            [(SmsMessage.Purpose.PHONE_VERIFY, '', SmsMessage.Status.SENT)],
        )
