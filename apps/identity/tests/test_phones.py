"""One number, one account, however it was typed.

`phone` is the USERNAME_FIELD, it is unique, and OTPs are keyed on it -- so
two spellings of one number are two accounts, and a student registered under
one of them can request a code against the other and never be able to sign in
with it.
"""

from django.db import IntegrityError

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP, User
from apps.identity.phones import normalize_phone
from apps.identity.tests.base import (
    ADMIN_USER_URL,
    CHECK_PHONE_URL,
    GET_OTP_URL,
    LOGIN_URL,
    VERIFY_OTP_URL,
    latest_code,
)

#: Every way the same number turns up in the wild.
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
        """It runs on both the serializer field and `create_user`, so it has
        to survive being applied twice."""
        for spelling in SPELLINGS:
            once = normalize_phone(spelling)
            self.assertEqual(normalize_phone(once), once)

    def test_it_leaves_nothing_and_none_alone(self):
        self.assertIsNone(normalize_phone(None))
        self.assertEqual(normalize_phone(""), "")

    def test_an_unrecognisable_number_is_not_mangled_into_a_wrong_one(self):
        """Deliberately not a validator -- rejecting here would strand a real
        but oddly-formatted number in the existing roster."""
        self.assertEqual(normalize_phone("+44 7700 900123"), "447700900123")


class ManagerNormalizationTests(ThrottledAPITestCase):
    def test_create_user_stores_the_canonical_form(self):
        """Covers the seed command, the shell and the spreadsheet import --
        none of which go through a serializer."""
        user = User.objects.create_user(phone="+8801810001111", name="Student")
        self.assertEqual(user.phone, CANONICAL)

    def test_a_second_spelling_is_a_duplicate_not_a_new_account(self):
        User.objects.create_user(phone=CANONICAL, name="First")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(phone="+8801810001111", name="Second")


class AuthEndpointNormalizationTests(ThrottledAPITestCase):
    """The flows a student actually walks through."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            phone=CANONICAL, name="Student", password="Str0ngPass!23"
        )

    def test_login_accepts_any_spelling(self):
        for spelling in SPELLINGS:
            response = self.client.post(
                LOGIN_URL, {"phone": spelling, "password": "Str0ngPass!23"}
            )
            self.assertEqual(response.status_code, 200, spelling)

    def test_phone_check_finds_the_account_from_any_spelling(self):
        for spelling in SPELLINGS:
            body = self.client.get(CHECK_PHONE_URL, {"phone": spelling}).json()
            self.assertTrue(body["exists"], spelling)

    def test_a_code_requested_one_way_verifies_the_other(self):
        """The failure this prevents: the code is texted to the student's real
        handset, and then does not work, because it was filed under a
        different spelling of their own number."""
        self.client.get(GET_OTP_URL, {"phone": "+8801810001111"})
        self.assertEqual(OTP.objects.filter(phone=CANONICAL).count(), 1)

        response = self.client.post(
            VERIFY_OTP_URL, {"phone": "8801810001111", "otp": latest_code(CANONICAL)}
        )
        self.assertEqual(response.status_code, 200)

    def test_the_resend_cooldown_is_not_reset_by_respelling_the_number(self):
        """Otherwise the cooldown is trivially bypassed and the SMS bill with
        it -- seven spellings, seven messages."""
        self.client.get(GET_OTP_URL, {"phone": CANONICAL})
        for spelling in SPELLINGS[1:]:
            self.client.get(GET_OTP_URL, {"phone": spelling})
        self.assertEqual(OTP.objects.count(), 1)

    def test_punctuation_only_is_a_bad_request(self):
        response = self.client.get(CHECK_PHONE_URL, {"phone": "---"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])


class AdminCreateNormalizationTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token

        self.admin = User.objects.create_user(
            phone="01710000031", name="Admin", password="Str0ngPass!23",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"
        }

    def test_admin_created_users_are_normalised(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Typed With Country Code", "phone": "+8801810002222"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["phone"], "01810002222")

    def test_a_respelt_duplicate_is_a_422_not_a_500(self):
        """`UniqueValidator` only catches this because the field normalises in
        `to_internal_value`, which DRF runs before its validators. The other
        order reaches the database and raises IntegrityError."""
        User.objects.create_user(phone="01810003333", name="Existing")

        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Duplicate", "phone": "+8801810003333"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])
