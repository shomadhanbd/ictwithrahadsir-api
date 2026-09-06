"""Shared fixtures for the identity suite.

The URLs are resolved once, by name, so a route that is renamed or moved
breaks here loudly instead of turning every test in the app into a 404.
"""

from django.urls import reverse

from apps.identity.models import OTP

CHECK_PHONE_URL = reverse('api:identity:v1:phone_check')
GET_OTP_URL = reverse('api:identity:v1:otp_request')
VERIFY_OTP_URL = reverse('api:identity:v1:otp_verify')
REGISTER_URL = reverse('api:identity:v1:user_register')
LOGIN_URL = reverse('api:identity:v1:user_login')
FORGET_PASSWORD_URL = reverse('api:identity:v1:password_forgot')
PASSWORD_RESET_URL = reverse('api:identity:v1:password_reset')
LOGOUT_URL = reverse('api:identity:v1:user_logout')
ME_URL = reverse('api:identity:v1:current_user')
ADMIN_USER_URL = reverse('api:identity:v1:admin-user-list')
ADMIN_USER_SEARCH_URL = reverse('api:identity:v1:admin_user_search')


def latest_code(phone):
    """The code that was just texted to `phone`.

    Tests read it out of the database rather than out of the SMS backend:
    what matters is that the code the user is holding works, not how it
    reached them.
    """
    return OTP.objects.filter(phone=phone).order_by("-created_at").first().code
