from rest_framework.test import APITestCase

from apps.identity.models import User
from apps.identity.tests.base import (
    LOGIN_URL,
    REGISTER_URL,
)


class LoginTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            phone="01810002222",
            email="s@example.com",
            name="Student",
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

    def test_email_is_no_longer_a_login(self):
        """Phone is the only identifier."""
        response = self.client.post(
            LOGIN_URL,
            {"email": "s@example.com", "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 422)

    def test_login_requires_a_phone(self):
        response = self.client.post(LOGIN_URL, {"password": "x"})
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
