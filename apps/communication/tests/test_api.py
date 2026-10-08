"""What the API answers when SMS is involved."""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.communication.gateways import SmsError


class SmsApiTests(TestCase):
    def test_an_otp_the_gateway_cannot_send_is_a_503(self):
        with mock.patch('apps.communication.services.get_gateway') as backend:
            backend.return_value.send.side_effect = SmsError('down')
            response = self.client.get(reverse('api:identity:otp_request'), {'phone': '01810001111'})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'message': "We couldn't send the SMS. Please try again shortly."})
