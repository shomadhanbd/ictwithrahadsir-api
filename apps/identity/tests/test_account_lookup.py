"""Looking up which sign-in step a phone needs, without sending a code."""

from unittest import mock

from rest_framework.test import APITestCase

from apps.identity.models import OTP, User
from apps.identity.tests.base import ACCOUNT_LOOKUP_URL


@mock.patch("apps.identity.services.send_sms")
class AccountLookupTests(APITestCase):
    def lookup(self, phone):
        return self.client.get(ACCOUNT_LOOKUP_URL, {"phone": phone})

    def test_an_account_with_a_password_signs_in_with_it(self, send_sms):
        User.objects.create_user(phone="01810006666", name="Student", password="Str0ngPass!23")

        response = self.lookup("01810006666")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"user_exist": True, "password_exist": True})

    def test_a_half_registered_account_has_no_password(self, send_sms):
        User.objects.create_unverified("01810006667")

        response = self.lookup("01810006667")

        self.assertEqual(response.data, {"user_exist": True, "password_exist": False})

    def test_an_unknown_phone_has_no_account(self, send_sms):
        response = self.lookup("01810006668")

        self.assertEqual(response.data, {"user_exist": False, "password_exist": False})

    def test_no_code_is_issued_or_sent(self, send_sms):
        User.objects.create_user(phone="01810006666", name="Student", password="Str0ngPass!23")

        self.lookup("01810006666")
        self.lookup("01810006668")

        self.assertFalse(OTP.objects.exists())
        send_sms.assert_not_called()

    def test_an_invalid_phone_is_refused(self, send_sms):
        response = self.lookup("12345")

        self.assertGreaterEqual(response.status_code, 400)
        self.assertLess(response.status_code, 500)
