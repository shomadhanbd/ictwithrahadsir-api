from unittest import mock

from django.urls import reverse

from rest_framework.test import APITestCase

from apps.identity.models import OTP

GET_OTP_URL = reverse('api:identity:otp_request')
VERIFY_OTP_URL = reverse('api:identity:otp_verify')
REGISTER_URL = reverse('api:identity:user_register')
LOGIN_URL = reverse('api:identity:user_login')
FORGET_PASSWORD_URL = reverse('api:identity:password_forgot')
PASSWORD_RESET_URL = reverse('api:identity:password_reset')
PASSWORD_RESET_CHECK_URL = reverse('api:identity:password_reset_check')
LOGOUT_URL = reverse('api:identity:user_logout')
ME_URL = reverse('api:identity:current_user')
ADMIN_USER_URL = reverse('api:identity:admin_user_list')
ADMIN_USER_SEARCH_URL = reverse('api:identity:admin_user_search')


#: The code every `FixedOtpCodeTestCase` will produce. Deliberately not
#: "000000", which several suites use as their known-wrong guess.
TEST_OTP_CODE = "123456"


class FixedOtpCodeTestCase(APITestCase):
    """Pins the OTP generator so a test knows what to submit."""

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch("apps.identity.services.get_random_string", return_value=TEST_OTP_CODE))


def latest_code(phone):
    """The code on the newest row for `phone`."""
    otp = OTP.objects.filter(phone=phone).order_by("-created_at").first()
    assert otp is not None, f"no OTP was issued for {phone}"
    return otp.code
