from unittest import mock

from django.urls import reverse

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP

CHECK_PHONE_URL = reverse('api:identity:phone_check')
GET_OTP_URL = reverse('api:identity:otp_request')
VERIFY_OTP_URL = reverse('api:identity:otp_verify')
REGISTER_URL = reverse('api:identity:user_register')
LOGIN_URL = reverse('api:identity:user_login')
FORGET_PASSWORD_URL = reverse('api:identity:password_forgot')
PASSWORD_RESET_URL = reverse('api:identity:password_reset')
LOGOUT_URL = reverse('api:identity:user_logout')
ME_URL = reverse('api:identity:current_user')
ADMIN_USER_URL = reverse('api:identity:admin_user_list')
ADMIN_USER_SEARCH_URL = reverse('api:identity:admin_user_search')


#: The code every `FixedOtpCodeTestCase` will produce. Deliberately not
#: "000000", which several suites use as their known-wrong guess.
TEST_OTP_CODE = "123456"


class FixedOtpCodeTestCase(ThrottledAPITestCase):
    """Pins the OTP generator so a test knows what to submit.

    `OTP.issue` builds its code with `get_random_string`; patching that is
    what makes every issued code `TEST_OTP_CODE`.
    """

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch("apps.identity.models.get_random_string", return_value=TEST_OTP_CODE))


def latest_code(phone):
    """The code on the newest row for `phone`.

    Asserts a row actually exists first, which is the half of this helper
    several tests genuinely lean on.
    """
    otp = OTP.objects.filter(phone=phone).order_by("-created_at").first()
    assert otp is not None, f"no OTP was issued for {phone}"
    return otp.code
