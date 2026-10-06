from unittest import mock

from django.conf import settings
from django.utils import timezone

from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    FORGET_PASSWORD_URL,
    GET_OTP_URL,
    PASSWORD_RESET_CHECK_URL,
    PASSWORD_RESET_URL,
    VERIFY_OTP_URL,
    FixedOtpCodeTestCase,
    latest_code,
)


class OtpCooldownTests(FixedOtpCodeTestCase):
    phone = "01810007777"

    def test_get_otp_stays_available_but_stops_sending(self):
        self.assertEqual(self.client.get(GET_OTP_URL, {"phone": self.phone}).status_code, 200)

        response = self.client.get(GET_OTP_URL, {"phone": self.phone})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_exist"], False)
        self.assertGreater(body["resend_in"], 0)
        self.assertEqual(OTP.objects.filter(phone=self.phone).count(), 1)

    def test_a_new_code_is_sent_once_the_cooldown_lapses(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        stale = timezone.now() - timezone.timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS + 1)
        OTP.objects.filter(phone=self.phone).update(created_at=stale)

        body = self.client.get(GET_OTP_URL, {"phone": self.phone}).json()
        self.assertEqual(body["message"], "OTP sent.")
        self.assertEqual(body["resend_in"], 0)
        self.assertEqual(OTP.objects.filter(phone=self.phone).count(), 2)

    def test_forget_password_shares_the_cooldown(self):
        User.objects.create_user(phone=self.phone, name="X", password="Str0ngPass!23")
        first = self.client.post(FORGET_PASSWORD_URL, {"phone": self.phone})
        self.assertEqual(first.status_code, 200)
        second = self.client.post(FORGET_PASSWORD_URL, {"phone": self.phone})
        self.assertEqual(second.status_code, 429)


class OtpBruteForceTests(FixedOtpCodeTestCase):
    phone = "01810008888"

    def setUp(self):
        super().setUp()
        User.objects.create_user(phone=self.phone, name="Victim", password="Str0ngPass!23")
        self.client.get(GET_OTP_URL, {"phone": self.phone})

    def _guess(self, code="000000"):
        return self.client.post(
            VERIFY_OTP_URL,
            {"phone": self.phone, "otp": code},
        )

    def test_code_is_burned_after_max_attempts(self):
        for _ in range(settings.OTP_MAX_ATTEMPTS):
            self.assertEqual(self._guess().status_code, 422)

        real = latest_code(self.phone)
        self.assertEqual(self._guess(real).status_code, 422)

    def test_wrong_guesses_are_counted(self):
        self._guess()
        self._guess()
        newest = OTP.objects.filter(phone=self.phone).order_by("-created_at").first()
        self.assertEqual(newest.attempts, 2)

    def test_the_cap_holds_when_guesses_race(self):
        """A guess that read the row before others used up the attempts is still refused."""
        stale = OTP.objects.filter(phone=self.phone).latest("created_at")
        OTP.objects.filter(pk=stale.pk).update(attempts=settings.OTP_MAX_ATTEMPTS)

        with mock.patch.object(type(OTP.objects), "latest_for", return_value=stale):
            self.assertEqual(self._guess(stale.code).status_code, 422)
        stale.refresh_from_db()
        self.assertIsNone(stale.consumed_at)
        self.assertEqual(stale.attempts, settings.OTP_MAX_ATTEMPTS)

    def test_a_right_guess_is_not_counted_as_a_failed_one(self):
        self._guess()
        self.assertEqual(self._guess(latest_code(self.phone)).status_code, 200)
        self.assertEqual(OTP.objects.filter(phone=self.phone).latest("created_at").attempts, 1)

    def test_expired_code_is_refused(self):
        stale = timezone.now() - timezone.timedelta(seconds=settings.OTP_TTL_SECONDS + 1)
        OTP.objects.filter(phone=self.phone).update(created_at=stale)
        self.assertEqual(self._guess(latest_code(self.phone)).status_code, 422)


class OtpPurposeTests(FixedOtpCodeTestCase):
    phone = "01810006666"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone=self.phone, name="Student", password="Str0ngPass!23")

    def _reset_with(self, code):
        return self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": self.phone,
                "otp": code,
                "password": "N3wStr0ng!pass",
                "password_confirmation": "N3wStr0ng!pass",
            },
        )

    def test_a_login_code_cannot_reset_the_password(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        login_code = latest_code(self.phone)

        response = self._reset_with(login_code)
        self.assertEqual(response.status_code, 422)
        self.assertIn("otp", response.json()["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ngPass!23"))

        verified = self.client.post(VERIFY_OTP_URL, {"phone": self.phone, "otp": login_code})
        self.assertEqual(verified.status_code, 200)

    def test_a_reset_code_cannot_mint_a_session_token(self):
        self.client.post(FORGET_PASSWORD_URL, {"phone": self.phone})
        reset_code = latest_code(self.phone)

        response = self.client.post(VERIFY_OTP_URL, {"phone": self.phone, "otp": reset_code})
        self.assertEqual(response.status_code, 422)
        self.assertIn("otp", response.json()["errors"])

    def test_a_reset_code_still_resets(self):
        self.client.post(FORGET_PASSWORD_URL, {"phone": self.phone})
        self.assertEqual(self._reset_with(latest_code(self.phone)).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3wStr0ng!pass"))


class OtpHourlyCapTests(FixedOtpCodeTestCase):
    """The limits that protect the SMS bill."""

    phone = "01810002200"

    def send(self, phone=None):
        return self.client.get(GET_OTP_URL, {"phone": phone or self.phone})

    def lapse_cooldown(self, phone=None):
        """Age every code past the cooldown."""
        stale = timezone.now() - timezone.timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS + 1)
        rows = OTP.objects.all() if phone is None else OTP.objects.filter(phone=phone)
        rows.update(created_at=stale)

    def test_the_send_records_the_client_hints_it_was_given(self):
        self.client.get(
            GET_OTP_URL,
            {"phone": self.phone},
            HTTP_X_PLATFORM="android",
            HTTP_X_APP_VERSION="1.2.0",
        )
        self.assertEqual(
            OTP.objects.get(phone=self.phone).meta,
            {"platform": "android", "app_version": "1.2.0"},
        )

    def test_the_send_records_nothing_when_no_hints_are_sent(self):
        self.send()
        self.assertEqual(OTP.objects.get(phone=self.phone).meta, {})

    def test_one_number_stops_at_the_hourly_cap(self):
        for _ in range(settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR):
            self.send()
            self.lapse_cooldown()

        response = self.send()
        self.assertEqual(response.status_code, 200, "the endpoint must stay 200 and report a wait")
        self.assertGreater(response.json()["resend_in"], 0)
        self.assertEqual(
            OTP.objects.filter(phone=self.phone).count(),
            settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR,
            "the capped request must not have spent an SMS",
        )

    def test_the_cap_is_per_number_not_global(self):
        """Each number carries its own allowance."""
        for _ in range(settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR):
            self.send()
            self.lapse_cooldown()

        fresh = "01810098765"
        self.assertEqual(self.send(phone=fresh).json()["resend_in"], 0)
        self.assertTrue(OTP.objects.filter(phone=fresh).exists())

    def test_the_cap_frees_up_once_the_window_passes(self):
        for _ in range(settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR):
            self.send()
            self.lapse_cooldown()

        OTP.objects.filter(phone=self.phone).update(created_at=timezone.now() - timezone.timedelta(hours=2))
        self.assertEqual(self.send().json()["resend_in"], 0)

    def test_forget_password_throttles_on_the_cap(self):
        User.objects.create_user(phone=self.phone, name="X", password="Str0ngPass!23")
        for _ in range(settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR):
            self.send()
            self.lapse_cooldown()

        self.assertEqual(self.client.post(FORGET_PASSWORD_URL, {"phone": self.phone}).status_code, 429)


class DemoAccountTests(FixedOtpCodeTestCase):
    """The reviewer escape hatch, which is off unless DEMO_PHONE is set."""

    phone = "01810000000"

    def test_it_is_off_by_default(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        response = self.client.post(VERIFY_OTP_URL, {"phone": self.phone, "otp": "000000"})
        self.assertEqual(response.status_code, 422)

    def test_the_demo_number_spends_no_sms(self):
        with self.settings(DEMO_PHONE=self.phone):
            self.assertEqual(self.client.get(GET_OTP_URL, {"phone": self.phone}).status_code, 200)
        self.assertFalse(OTP.objects.filter(phone=self.phone).exists())

    def test_the_demo_code_verifies(self):
        with self.settings(DEMO_PHONE=self.phone, DEMO_OTP_CODE="000000"):
            self.client.get(GET_OTP_URL, {"phone": self.phone})
            response = self.client.post(VERIFY_OTP_URL, {"phone": self.phone, "otp": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_a_wrong_code_on_the_demo_number_is_still_refused(self):
        with self.settings(DEMO_PHONE=self.phone, DEMO_OTP_CODE="000000"):
            self.client.get(GET_OTP_URL, {"phone": self.phone})
            response = self.client.post(VERIFY_OTP_URL, {"phone": self.phone, "otp": "999999"})
        self.assertEqual(response.status_code, 422)

    def test_other_numbers_do_not_take_the_demo_code(self):
        other = "01810001212"
        with self.settings(DEMO_PHONE=self.phone, DEMO_OTP_CODE="000000"):
            self.client.get(GET_OTP_URL, {"phone": other})
            response = self.client.post(VERIFY_OTP_URL, {"phone": other, "otp": "000000"})
        self.assertEqual(response.status_code, 422)

    def test_the_demo_code_does_not_reset_the_demo_password(self):
        """Anyone knows the reviewer's code; it must not let them lock the reviewer out."""
        User.objects.create_user(phone=self.phone, name="Reviewer", password="Str0ngPass!23")
        body = {
            "phone": self.phone,
            "otp": "000000",
            "password": "N3wStr0ng!pass",
            "password_confirmation": "N3wStr0ng!pass",
        }
        with self.settings(DEMO_PHONE=self.phone, DEMO_OTP_CODE="000000"):
            check = self.client.post(PASSWORD_RESET_CHECK_URL, {"phone": self.phone, "otp": "000000"})
            reset = self.client.post(PASSWORD_RESET_URL, body)
        self.assertEqual((check.status_code, reset.status_code), (422, 422))
        self.assertTrue(User.objects.get(phone=self.phone).check_password("Str0ngPass!23"))
