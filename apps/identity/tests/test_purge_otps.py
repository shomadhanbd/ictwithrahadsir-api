from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.identity.models import OTP
from apps.identity.selectors import seconds_until_resend
from apps.identity.services import issue_otp

PHONE = "01810007070"


class PurgeExpiredOtpsTests(TestCase):
    def age(self, otp, minutes):
        OTP.objects.filter(pk=otp.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=minutes))

    def test_the_last_hour_is_kept_so_the_hourly_cap_survives_a_purge(self):
        for _ in range(settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR):
            self.age(issue_otp(PHONE, OTP.Purpose.VERIFY), minutes=10)
        self.assertGreater(seconds_until_resend(PHONE), 0)

        call_command("purge_expired_otps", stdout=StringIO())

        self.assertEqual(OTP.objects.count(), settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR)
        self.assertGreater(seconds_until_resend(PHONE), 0)

    def test_codes_older_than_the_hour_are_removed(self):
        self.age(issue_otp(PHONE, OTP.Purpose.VERIFY), minutes=61)
        call_command("purge_expired_otps", stdout=StringIO())
        self.assertFalse(OTP.objects.exists())

    def test_a_shorter_window_cannot_go_under_the_hour(self):
        self.age(issue_otp(PHONE, OTP.Purpose.VERIFY), minutes=10)
        call_command("purge_expired_otps", "--days", "0", stdout=StringIO())
        self.assertEqual(OTP.objects.count(), 1)
