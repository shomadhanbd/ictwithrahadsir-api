"""Registration: get a code, verify it, complete the profile."""

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    CHECK_PHONE_URL,
    GET_OTP_URL,
    REGISTER_URL,
    VERIFY_OTP_URL,
    latest_code,
)


class AuthFlowTests(ThrottledAPITestCase):
    """Registration is a three-step dance: get-otp -> verify-otp (which
    creates a bare row and returns a token) -> register (which fills in the
    profile and sets the password)."""

    def setUp(self):
        super().setUp()
        self.phone = "01810001111"

    def test_check_phone_reports_existence(self):
        response = self.client.get(CHECK_PHONE_URL, {"phone": self.phone})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"exists": False})

        User.objects.create_user(phone=self.phone, name="Existing")
        response = self.client.get(CHECK_PHONE_URL, {"phone": self.phone})
        self.assertEqual(response.json(), {"exists": True})

    def test_check_phone_requires_a_phone(self):
        """Reading the raw query param meant a missing `phone` was answered
        as "no account exists for the empty string" -- a 200 for a request
        that never asked anything."""
        response = self.client.get(CHECK_PHONE_URL)
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_check_phone_is_throttled(self):
        """It answers "is this number registered?" and nothing else, so
        unthrottled it can be walked across the whole 01XXXXXXXXX range."""
        statuses = [
            self.client.get(CHECK_PHONE_URL, {"phone": f"018100200{i:02d}"}).status_code
            for i in range(15)
        ]
        self.assertIn(429, statuses, f"no throttle fired: {statuses}")

    def test_get_otp_requires_phone(self):
        response = self.client.get(GET_OTP_URL)
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_get_otp_reports_unknown_number(self):
        response = self.client.get(GET_OTP_URL, {"phone": self.phone})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_exist"], False)
        self.assertEqual(body["password_exist"], False)
        self.assertEqual(body["message"], "OTP sent.")
        self.assertEqual(OTP.objects.filter(phone=self.phone).count(), 1)

    def test_get_otp_reports_registered_number(self):
        User.objects.create_user(phone=self.phone, name="X", password="Str0ngPass!23")
        body = self.client.get(GET_OTP_URL, {"phone": self.phone}).json()
        self.assertEqual(body["user_exist"], True)
        self.assertEqual(body["password_exist"], True)

    def test_verify_otp_rejects_wrong_code(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        response = self.client.post(
            VERIFY_OTP_URL,
            {"phone": self.phone, "otp": "000000"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("otp", response.json()["errors"])

    def test_verify_otp_creates_bare_user_and_returns_null_user(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        response = self.client.post(
            VERIFY_OTP_URL,
            {"phone": self.phone, "otp": latest_code(self.phone)},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["user"])
        self.assertTrue(body["token"])

        user = User.objects.get(phone=self.phone)
        self.assertIsNotNone(user.phone_verified_at)
        self.assertFalse(user.has_usable_password())

    def test_verify_otp_returns_existing_user(self):
        User.objects.create_user(phone=self.phone, name="Existing", password="Str0ngPass!23")
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        response = self.client.post(
            VERIFY_OTP_URL,
            {"phone": self.phone, "otp": latest_code(self.phone)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["name"], "Existing")

    def test_otp_is_single_use(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        code = latest_code(self.phone)
        payload = {"phone": self.phone, "otp": code}
        first = self.client.post(VERIFY_OTP_URL, payload)
        self.assertEqual(first.status_code, 200)
        second = self.client.post(VERIFY_OTP_URL, payload)
        self.assertEqual(second.status_code, 422)

    def _verified_phone(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        self.client.post(
            VERIFY_OTP_URL,
            {"phone": self.phone, "otp": latest_code(self.phone)},
        )

    def test_register_completes_the_profile(self):
        self._verified_phone()
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "New Student",
                "phone": self.phone,
                "institute": "Dhaka College",
                "educational_session": "2025-26",
                "password": "Str0ngPass!23",
                "password_confirmation": "Str0ngPass!23",
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["token"])
        self.assertEqual(body["user"]["name"], "New Student")

        user = User.objects.get(phone=self.phone)
        self.assertEqual(user.institution, "Dhaka College")
        self.assertTrue(user.check_password("Str0ngPass!23"))

    def test_register_requires_a_verified_phone(self):
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "No OTP",
                "phone": "01899999999",
                "password": "Str0ngPass!23",
                "password_confirmation": "Str0ngPass!23",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_register_rejects_mismatched_confirmation(self):
        self._verified_phone()
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "New Student",
                "phone": self.phone,
                "password": "Str0ngPass!23",
                "password_confirmation": "different",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("password_confirmation", response.json()["errors"])

    def test_register_is_rejected_twice(self):
        self._verified_phone()
        payload = {
            "name": "New Student",
            "phone": self.phone,
            "password": "Str0ngPass!23",
            "password_confirmation": "Str0ngPass!23",
        }
        self.client.post(REGISTER_URL, payload)
        response = self.client.post(REGISTER_URL, payload)
        self.assertEqual(response.status_code, 422)
