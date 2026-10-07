"""Signing up with OTP: request a code, verify it, register."""

from django.conf import settings
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.academic.models import ClassLevel, Group
from apps.core.testing import next_slug
from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    GET_OTP_URL,
    REGISTER_URL,
    VERIFY_OTP_URL,
    FixedOtpCodeTestCase,
    latest_code,
)


class AuthFlowTests(FixedOtpCodeTestCase):
    def setUp(self):
        super().setUp()
        self.phone = "01810001111"

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

    def _verified_phone(self, phone=None):
        phone = phone or self.phone
        self.client.get(GET_OTP_URL, {"phone": phone})
        response = self.client.post(
            VERIFY_OTP_URL,
            {"phone": phone, "otp": latest_code(phone)},
        )
        return {"HTTP_AUTHORIZATION": f"Bearer {response.json()['token']}"}

    def test_register_completes_the_profile(self):
        auth = self._verified_phone()
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
            **auth,
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["token"])
        self.assertEqual(body["user"]["name"], "New Student")

        user = User.objects.get(phone=self.phone)
        self.assertEqual(user.student.institution, "Dhaka College")
        self.assertEqual(user.student.educational_session, "2025-26")
        self.assertTrue(user.check_password("Str0ngPass!23"))
        self.assertEqual(body["user"]["student"]["institution"], "Dhaka College")

    def test_register_records_the_class_and_group(self):
        hsc, science = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="Science"),
        )
        auth = self._verified_phone()
        body = {
            "name": "New Student",
            "phone": self.phone,
            "class_level_id": hsc.pk,
            "group_id": science.pk,
            "password": "Str0ngPass!23",
            "password_confirmation": "Str0ngPass!23",
        }
        self.assertEqual(self.client.post(REGISTER_URL, body, **auth).status_code, 201)
        student = User.objects.get(phone=self.phone).student
        self.assertEqual((student.class_level_id, student.group_id), (hsc.pk, science.pk))

    def test_register_refuses_a_common_group(self):
        hsc, general = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="General", is_common=True),
        )
        auth = self._verified_phone()
        body = {
            "name": "New Student",
            "phone": self.phone,
            "class_level_id": hsc.pk,
            "group_id": general.pk,
            "password": "Str0ngPass!23",
            "password_confirmation": "Str0ngPass!23",
        }
        response = self.client.post(REGISTER_URL, body, **auth)
        self.assertEqual(response.status_code, 422)
        self.assertIn("group_id", response.json()["errors"])

    def test_register_requires_a_verified_session(self):
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "No OTP",
                "phone": "01899999999",
                "password": "Str0ngPass!23",
                "password_confirmation": "Str0ngPass!23",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_an_abandoned_signup_cannot_be_claimed_by_a_stranger(self):
        self._verified_phone()

        response = self.client.post(
            REGISTER_URL,
            {
                "name": "Impostor",
                "phone": self.phone,
                "password": "Str0ngPass!23",
                "password_confirmation": "Str0ngPass!23",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.get(phone=self.phone).has_usable_password())

    def test_a_session_cannot_register_someone_elses_number(self):
        auth = self._verified_phone()
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "Impostor",
                "phone": "01899999999",
                "password": "Str0ngPass!23",
                "password_confirmation": "Str0ngPass!23",
            },
            **auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_a_stale_verification_is_refused(self):
        auth = self._verified_phone()
        User.objects.filter(phone=self.phone).update(
            phone_verified_at=timezone.now() - timezone.timedelta(seconds=settings.REGISTRATION_WINDOW_SECONDS + 60)
        )
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "Too Slow",
                "phone": self.phone,
                "password": "Str0ngPass!23",
                "password_confirmation": "Str0ngPass!23",
            },
            **auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_register_rejects_mismatched_confirmation(self):
        auth = self._verified_phone()
        response = self.client.post(
            REGISTER_URL,
            {
                "name": "New Student",
                "phone": self.phone,
                "password": "Str0ngPass!23",
                "password_confirmation": "different",
            },
            **auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("password_confirmation", response.json()["errors"])

    def test_register_is_rejected_twice(self):
        auth = self._verified_phone()
        payload = {
            "name": "New Student",
            "phone": self.phone,
            "password": "Str0ngPass!23",
            "password_confirmation": "Str0ngPass!23",
        }
        self.client.post(REGISTER_URL, payload, **auth)
        response = self.client.post(REGISTER_URL, payload, **auth)
        self.assertEqual(response.status_code, 422)


class OtpVerifyRepeatTests(FixedOtpCodeTestCase):
    phone = "01810002020"

    def _verify(self):
        self.client.get(GET_OTP_URL, {"phone": self.phone})
        return self.client.post(VERIFY_OTP_URL, {"phone": self.phone, "otp": latest_code(self.phone)})

    def _lapse_cooldown(self):
        OTP.objects.filter(phone=self.phone).update(created_at=timezone.now() - timezone.timedelta(seconds=999))

    def test_an_abandoned_signup_still_reports_the_user_as_new(self):
        self.assertIsNone(self._verify().json()["user"])
        self._lapse_cooldown()

        self.assertIsNone(self._verify().json()["user"])

    def test_a_registered_user_is_returned(self):
        User.objects.create_user(phone=self.phone, name="Done", password="Str0ngPass!23")
        self.assertEqual(self._verify().json()["user"]["name"], "Done")


class RegistrationTests(APITestCase):
    def test_registration_cannot_be_spammed_without_verified_sessions(self):
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
        self.assertEqual(set(statuses), {401}, f'unauthenticated register got through: {statuses}')
