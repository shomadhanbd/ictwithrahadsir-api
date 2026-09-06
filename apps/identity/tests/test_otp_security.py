"""The two protections on a one-time code: how often one can be asked
for, and how many times one can be guessed.

Both matter because a verified code mints a full auth token -- an
unlimited-guess six-digit number is an account takeover, and an
unlimited-resend endpoint is an SMS bill.
"""

from django.conf import settings
from django.utils import timezone

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    FORGET_PASSWORD_URL,
    GET_OTP_URL,
    VERIFY_OTP_URL,
    latest_code,
)


class OtpCooldownTests(ThrottledAPITestCase):
    """OTP_RESEND_COOLDOWN_SECONDS existed in settings but was never read, so
    the public get-otp endpoint could be used to bombard a number with SMS."""

    phone = "01810007777"

    def test_get_otp_stays_available_but_stops_sending(self):
        # The client calls get-otp on every login attempt, so it must keep
        # answering 200 -- it just must not send a second SMS.
        self.assertEqual(self.client.get(GET_OTP_URL, {"phone": self.phone}).status_code, 200)

        response = self.client.get(GET_OTP_URL, {"phone": self.phone})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_exist"], False)
        self.assertGreater(body["resend_in"], 0)
        self.assertEqual(OTP.objects.filter(phone=self.phone).count(), 1)

    def test_a_new_code_is_sent_once_the_cooldown_lapses(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        stale = timezone.now() - timezone.timedelta(
            seconds=settings.OTP_RESEND_COOLDOWN_SECONDS + 1
        )
        OTP.objects.filter(phone=self.phone).update(created_at=stale)

        body = self.client.get(GET_OTP_URL, {"phone": self.phone}).json()
        self.assertEqual(body["message"], "OTP sent.")
        self.assertEqual(body["resend_in"], 0)
        self.assertEqual(OTP.objects.filter(phone=self.phone).count(), 2)

    def test_forget_password_shares_the_cooldown(self):
        User.objects.create_user(phone=self.phone, name="X", password="Str0ngPass!23")
        first = self.client.post(
            FORGET_PASSWORD_URL, {"phone": self.phone}
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            FORGET_PASSWORD_URL, {"phone": self.phone}
        )
        self.assertEqual(second.status_code, 429)

class OtpBruteForceTests(ThrottledAPITestCase):
    """A verified OTP mints a full auth token, so an unlimited-guess 6-digit
    code was an account-takeover path."""

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
        for _ in range(OTP.MAX_ATTEMPTS):
            self.assertEqual(self._guess().status_code, 422)

        # Even the correct code is now refused: the attacker must request a
        # new one, which the resend cooldown rate-limits.
        real = latest_code(self.phone)
        self.assertEqual(self._guess(real).status_code, 422)

    def test_wrong_guesses_are_counted(self):
        self._guess()
        self._guess()
        self.assertEqual(OTP.latest_for(self.phone).attempts, 2)

    def test_expired_code_is_refused(self):
        stale = timezone.now() - timezone.timedelta(seconds=settings.OTP_TTL_SECONDS + 1)
        OTP.objects.filter(phone=self.phone).update(created_at=stale)
        self.assertEqual(self._guess(latest_code(self.phone)).status_code, 422)
