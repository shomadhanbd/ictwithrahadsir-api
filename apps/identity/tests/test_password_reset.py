from unittest import mock

from rest_framework.authtoken.models import Token

from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    FORGET_PASSWORD_URL,
    ME_URL,
    PASSWORD_RESET_URL,
    FixedOtpCodeTestCase,
    latest_code,
)


class PasswordResetTests(FixedOtpCodeTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone="01810003333", name="Student", password="Str0ngPass!23")

    def test_an_unknown_phone_gets_the_same_answer_and_no_sms(self):
        """The reply must not tell who has an account."""
        unknown, known = "01800000000", self.user.phone
        with mock.patch("apps.communication.services.get_gateway") as backend:
            replies = [self.client.post(FORGET_PASSWORD_URL, {"phone": phone}) for phone in (unknown, known)]
        self.assertEqual([r.status_code for r in replies], [200, 200])
        self.assertEqual(replies[0].json(), replies[1].json())
        self.assertEqual([c.args[0] for c in backend.return_value.send.call_args_list], [known])

    def test_an_unknown_phone_issues_no_code(self):
        self.client.post(FORGET_PASSWORD_URL, {"phone": "01800000000"})
        self.assertFalse(OTP.objects.filter(phone="01800000000").exists())

    def test_forget_password_issues_otp(self):
        response = self.client.post(
            FORGET_PASSWORD_URL,
            {"phone": self.user.phone},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "OTP sent."})
        self.assertEqual(OTP.objects.filter(phone=self.user.phone).count(), 1)

    def test_password_reset_changes_the_password(self):
        self.client.post(
            FORGET_PASSWORD_URL,
            {"phone": self.user.phone},
        )
        response = self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": self.user.phone,
                "otp": latest_code(self.user.phone),
                "password": "N3wStr0ng!pass",
                "password_confirmation": "N3wStr0ng!pass",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3wStr0ng!pass"))

    def test_password_reset_rejects_mismatch(self):
        response = self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": self.user.phone,
                "otp": "000000",
                "password": "N3wStr0ng!pass",
                "password_confirmation": "D1fferent!pass",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("password_confirmation", response.json()["errors"])

    def test_password_reset_rejects_bad_otp(self):
        response = self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": self.user.phone,
                "otp": "000000",
                "password": "N3wStr0ng!pass",
                "password_confirmation": "N3wStr0ng!pass",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("otp", response.json()["errors"])


class PasswordResetSecurityTests(FixedOtpCodeTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone="01810004321", name="Student", password="Str0ngPass!23")
        self.stale_token = Token.objects.create(user=self.user).key
        self.client.post(
            FORGET_PASSWORD_URL,
            {"phone": self.user.phone},
        )

    def _reset(self, password):
        return self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": self.user.phone,
                "otp": latest_code(self.user.phone),
                "password": password,
                "password_confirmation": password,
            },
        )

    def test_weak_password_is_rejected(self):
        response = self._reset("1234")
        self.assertEqual(response.status_code, 422)
        self.assertIn("password", response.json()["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ngPass!23"))

    def test_a_rejected_password_does_not_burn_the_code(self):
        self.assertEqual(self._reset("1234").status_code, 422)

        self.assertEqual(self._reset("N3wStr0ng!pass").status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3wStr0ng!pass"))

    def test_an_unknown_phone_does_not_burn_the_code(self):
        response = self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": "01800000000",
                "otp": latest_code(self.user.phone),
                "password": "N3wStr0ng!pass",
                "password_confirmation": "N3wStr0ng!pass",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(list(response.json()["errors"]), ["otp"])  # the same answer as a wrong code
        self.assertEqual(self._reset("N3wStr0ng!pass").status_code, 200)

    def test_reset_invalidates_previously_issued_tokens(self):
        response = self._reset("N3wStr0ng!pass")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["token"], self.stale_token)
        self.assertFalse(Token.objects.filter(key=self.stale_token).exists())

        stale_auth = {"HTTP_AUTHORIZATION": f"Bearer {self.stale_token}"}
        self.assertEqual(self.client.get(ME_URL, **stale_auth).status_code, 401)
