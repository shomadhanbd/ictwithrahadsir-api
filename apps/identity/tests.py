"""Contract tests for the identity endpoints.

Written to pin the exact request/response shapes both frontends already
depend on (see the Laravel-compatible envelope in apps.core.api.exception_handler and
apps.core.api.pagination) before refactoring the views, so the function-based ->
class-based move is provably behaviour-preserving.
"""

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from apps.core.testing import ThrottledAPITestCase

from apps.identity.models import OTP, User

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
    return OTP.objects.filter(phone=phone).order_by("-created_at").first().code


class AuthFlowTests(ThrottledAPITestCase):
    """Registration is a three-step dance: get-otp -> verify-otp (which
    creates a bare row and returns a token) -> register (which fills in the
    profile and sets the password)."""

    def setUp(self):
        self.phone = "01810001111"

    def test_check_phone_reports_existence(self):
        response = self.client.get(CHECK_PHONE_URL, {"phone": self.phone})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"exists": False})

        User.objects.create_user(phone=self.phone, name="Existing")
        response = self.client.get(CHECK_PHONE_URL, {"phone": self.phone})
        self.assertEqual(response.json(), {"exists": True})

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


class LoginTests(ThrottledAPITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="01810002222", email="s@example.com", name="Student",
            password="Str0ngPass!23",
        )

    def test_login_with_phone(self):
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.user.phone, "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.assertEqual(response.json()["user"]["phone"], self.user.phone)

    def test_login_with_email(self):
        response = self.client.post(
            LOGIN_URL,
            {"email": "s@example.com", "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 200)

    def test_login_requires_phone_or_email(self):
        response = self.client.post(
            LOGIN_URL, {"password": "x"}
        )
        self.assertEqual(response.status_code, 422)

    def test_login_rejects_bad_password(self):
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.user.phone, "password": "wrong"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("password", response.json()["errors"])

    def test_login_rejects_inactive_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.user.phone, "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 422)


class PasswordResetTests(ThrottledAPITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="01810003333", name="Student", password="Str0ngPass!23"
        )

    def test_forget_password_requires_known_phone(self):
        response = self.client.post(
            FORGET_PASSWORD_URL, {"phone": "01800000000"},
        )
        self.assertEqual(response.status_code, 422)

    def test_forget_password_issues_otp(self):
        response = self.client.post(
            FORGET_PASSWORD_URL, {"phone": self.user.phone},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "OTP sent."})
        self.assertEqual(OTP.objects.filter(phone=self.user.phone).count(), 1)

    def test_password_reset_changes_the_password(self):
        self.client.post(
            FORGET_PASSWORD_URL, {"phone": self.user.phone},
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
                "phone": self.user.phone, "otp": "000000",
                "password": "a", "password_confirmation": "b",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("password_confirmation", response.json()["errors"])

    def test_password_reset_rejects_bad_otp(self):
        response = self.client.post(
            PASSWORD_RESET_URL,
            {
                "phone": self.user.phone, "otp": "000000",
                "password": "N3wStr0ng!pass", "password_confirmation": "N3wStr0ng!pass",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("otp", response.json()["errors"])


class MeAndLogoutTests(ThrottledAPITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="01810004444", name="Student", password="Str0ngPass!23"
        )
        self.token = Token.objects.create(user=self.user)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token.key}"}

    def test_me_requires_authentication(self):
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"message": "Unauthenticated."})

    def test_me_returns_the_current_user(self):
        response = self.client.get(ME_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["phone"], self.user.phone)

    def test_me_post_updates_the_profile(self):
        response = self.client.post(
            ME_URL, {"name": "Renamed"}, **self.auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Renamed")

    def test_logout_deletes_the_token(self):
        response = self.client.post(LOGOUT_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(Token.objects.filter(user=self.user).exists())


class LoginThrottleTests(ThrottledAPITestCase):
    """Nothing was rate limited before, so /api/login accepted password
    guesses as fast as they could be sent."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            phone='01810005555', name='Victim', password='Str0ngPass!23'
        )

    def guess(self, password='wrong'):
        return self.client.post(
            LOGIN_URL, {'phone': self.user.phone, 'password': password}, format='json'
        )

    def test_repeated_password_guesses_are_eventually_throttled(self):
        statuses = [self.guess().status_code for _ in range(15)]
        self.assertIn(429, statuses, f'no throttle fired: {statuses}')

    def test_the_throttle_also_stops_a_correct_password(self):
        # Otherwise an attacker could keep guessing and simply notice which
        # attempt stopped returning 422.
        for _ in range(15):
            self.guess()
        self.assertEqual(self.guess('Str0ngPass!23').status_code, 429)

    def test_the_limit_is_not_hit_by_ordinary_use(self):
        # A handful of typos must not lock a real user out.
        for _ in range(5):
            self.assertEqual(self.guess().status_code, 422)
        self.assertEqual(self.guess('Str0ngPass!23').status_code, 200)

    def test_the_throttled_response_keeps_the_error_envelope(self):
        for _ in range(15):
            self.guess()
        body = self.guess().json()
        self.assertIn('message', body)


class RegistrationThrottleTests(ThrottledAPITestCase):
    def test_registration_attempts_are_throttled(self):
        statuses = []
        for i in range(15):
            response = self.client.post(
                REGISTER_URL,
                {
                    'name': 'Spam',
                    'phone': f'018100600{i:02d}',
                    'password': 'Str0ngPass!23',
                    'password_confirmation': 'Str0ngPass!23',
                },
                format='json',
            )
            statuses.append(response.status_code)
        self.assertIn(429, statuses, f'no throttle fired: {statuses}')


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


class PasswordResetSecurityTests(ThrottledAPITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="01810004321", name="Student", password="Str0ngPass!23"
        )
        self.stale_token = Token.objects.create(user=self.user).key
        self.client.post(
            FORGET_PASSWORD_URL, {"phone": self.user.phone},
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
        # The register path always ran the configured validators; the reset
        # path did not, so any strength rule could be sidestepped.
        response = self._reset("1234")
        self.assertEqual(response.status_code, 422)
        self.assertIn("password", response.json()["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ngPass!23"))

    def test_reset_invalidates_previously_issued_tokens(self):
        response = self._reset("N3wStr0ng!pass")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["token"], self.stale_token)
        self.assertFalse(Token.objects.filter(key=self.stale_token).exists())

        stale_auth = {"HTTP_AUTHORIZATION": f"Bearer {self.stale_token}"}
        self.assertEqual(self.client.get(ME_URL, **stale_auth).status_code, 401)


class AdminRoleEscalationTests(ThrottledAPITestCase):
    """IsAdminRole admits instructors, so /admin/user must not let them hand
    out privileged roles or edit privileged accounts."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            phone="01710000009", name="Instructor", password="Str0ngPass!23",
            role=User.Role.INSTRUCTOR,
        )
        self.auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.instructor).key}"
        }
        self.admin = User.objects.create_user(
            phone="01710000010", name="Admin", password="Str0ngPass!23",
            role=User.Role.ADMIN, is_staff=True,
        )

    def test_instructor_cannot_create_an_admin(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Backdoor", "phone": "01810001234", "role": "admin"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(User.objects.filter(phone="01810001234").exists())

    def test_instructor_cannot_promote_themselves(self):
        response = self.client.patch(
            reverse('api:identity:v1:admin-user-detail', args=[self.instructor.pk]),
            {"role": "admin"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.instructor.refresh_from_db()
        self.assertEqual(self.instructor.role, User.Role.INSTRUCTOR)

    def test_instructor_cannot_reset_an_admins_password(self):
        response = self.client.patch(
            reverse('api:identity:v1:admin-user-detail', args=[self.admin.pk]),
            {"password": "Tak30v3r!pass"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("Str0ngPass!23"))

    def test_admin_can_still_create_an_admin(self):
        admin_auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"
        }
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Second Admin", "phone": "01810004321", "role": "admin"},
            **admin_auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_instructor_can_still_manage_students(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "A Student", "phone": "01810005678", "role": "student"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)


class AdminUserTests(ThrottledAPITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone="01710000001", name="Admin", password="Str0ngPass!23",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"
        }
        self.student = User.objects.create_user(
            phone="01810005555", name="Rahim Uddin", password="Str0ngPass!23"
        )

    def test_admin_endpoints_reject_students(self):
        student_auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.student).key}"
        }
        self.assertEqual(self.client.get(ADMIN_USER_URL, **student_auth).status_code, 403)

    def test_admin_user_list_is_paginated(self):
        response = self.client.get(ADMIN_USER_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("meta", body)
        self.assertEqual(body["meta"]["total"], 2)

    def test_admin_user_list_filters_by_role(self):
        response = self.client.get(ADMIN_USER_URL, {"role": "student"}, **self.auth)
        self.assertEqual(response.json()["meta"]["total"], 1)

    def test_admin_user_search(self):
        response = self.client.get(
            ADMIN_USER_SEARCH_URL, {"search": "Rahim"}, **self.auth
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Rahim Uddin")

    def test_admin_can_create_a_user(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {
                "name": "Created", "phone": "01810006666",
                "password": "Str0ngPass!23", "role": "student",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(phone="01810006666")
        self.assertTrue(created.check_password("Str0ngPass!23"))
