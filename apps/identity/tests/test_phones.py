from django.db import IntegrityError

from apps.core.phones import normalize_phone
from apps.core.testing import bearer
from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    ADMIN_USER_URL,
    GET_OTP_URL,
    LOGIN_URL,
    VERIFY_OTP_URL,
    FixedOtpCodeTestCase,
    latest_code,
)

SPELLINGS = [
    "01810001111",
    "+8801810001111",
    "8801810001111",
    "00880 1810001111",
    "1810001111",
    "018-1000-1111",
    "  01810001111  ",
]
CANONICAL = "01810001111"


class NormalizeFunctionTests(ThrottledAPITestCase):
    def test_every_spelling_collapses_to_one(self):
        self.assertEqual({normalize_phone(s) for s in SPELLINGS}, {CANONICAL})

    def test_it_is_idempotent(self):
        for spelling in SPELLINGS:
            once = normalize_phone(spelling)
            self.assertEqual(normalize_phone(once), once)

    def test_it_leaves_nothing_and_none_alone(self):
        self.assertIsNone(normalize_phone(None))
        self.assertEqual(normalize_phone(""), "")

    def test_a_number_from_another_country_is_refused(self):
        """A valid GB mobile is not a valid account here."""
        self.assertIsNone(normalize_phone("+44 7700 900123"))

    def test_a_string_that_is_not_a_number_at_all_is_refused(self):
        for junk in ("12345", "n/a", "hello", "0000000000", "+880"):
            with self.subTest(junk=junk):
                self.assertIsNone(normalize_phone(junk))

    def test_a_number_of_the_wrong_length_is_refused(self):
        self.assertIsNone(normalize_phone("0181000111"))
        self.assertIsNone(normalize_phone("018100011110"))

    def test_an_unassigned_operator_prefix_is_refused(self):
        """Bangladeshi mobiles run 013-019."""
        self.assertIsNone(normalize_phone("01210001111"))

    def test_every_live_operator_prefix_is_accepted(self):
        for prefix in ("013", "014", "015", "016", "017", "018", "019"):
            with self.subTest(prefix=prefix):
                self.assertEqual(normalize_phone(f"{prefix}10001111"), f"{prefix}10001111")


class ManagerNormalizationTests(ThrottledAPITestCase):
    def test_create_user_stores_the_canonical_form(self):
        user = User.objects.create_user(phone="+8801810001111", name="Student")
        self.assertEqual(user.phone, CANONICAL)

    def test_a_second_spelling_is_a_duplicate_not_a_new_account(self):
        User.objects.create_user(phone=CANONICAL, name="First")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(phone="+8801810001111", name="Second")


class AuthEndpointNormalizationTests(FixedOtpCodeTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone=CANONICAL, name="Student", password="Str0ngPass!23")

    def test_login_accepts_any_spelling(self):
        for spelling in SPELLINGS:
            response = self.client.post(LOGIN_URL, {"phone": spelling, "password": "Str0ngPass!23"})
            self.assertEqual(response.status_code, 200, spelling)

    def test_a_code_requested_one_way_verifies_the_other(self):
        self.client.get(GET_OTP_URL, {"phone": "+8801810001111"})
        self.assertEqual(OTP.objects.filter(phone=CANONICAL).count(), 1)

        response = self.client.post(VERIFY_OTP_URL, {"phone": "8801810001111", "otp": latest_code(CANONICAL)})
        self.assertEqual(response.status_code, 200)

    def test_the_resend_cooldown_is_not_reset_by_respelling_the_number(self):
        self.client.get(GET_OTP_URL, {"phone": CANONICAL})
        for spelling in SPELLINGS[1:]:
            self.client.get(GET_OTP_URL, {"phone": spelling})
        self.assertEqual(OTP.objects.count(), 1)

    def test_punctuation_only_is_a_bad_request(self):
        response = self.client.get(GET_OTP_URL, {"phone": "---"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])


class AdminCreateNormalizationTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            phone="01710000031",
            name="Admin",
            password="Str0ngPass!23",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.auth = bearer(self.admin)

    def test_admin_created_users_are_normalised(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Typed With Country Code", "phone": "+8801810002222", "password": "Str0ngPass!23"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["phone"], "01810002222")

    def test_a_respelt_duplicate_is_a_422_not_a_500(self):
        User.objects.create_user(phone="01810003333", name="Existing")

        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Duplicate", "phone": "+8801810003333"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])
