"""Signing in with a password, and how long the token lasts."""

from django.test import override_settings
from django.utils import timezone

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.identity.models import User
from apps.identity.tests.base import (
    LOGIN_URL,
    ME_URL,
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


@override_settings(TOKEN_TTL_DAYS=90)
class TokenLifetimeTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone="01810004446", name="Student", password="Str0ngPass!23")
        self.token = Token.objects.create(user=self.user)
        Token.objects.filter(pk=self.token.pk).update(created=timezone.now() - timezone.timedelta(days=91))

    def test_an_expired_token_is_refused(self):
        response = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"message": "Your session has expired. Please sign in again."})

    def test_signing_in_again_issues_a_fresh_token(self):
        response = self.client.post(LOGIN_URL, {"phone": self.user.phone, "password": "Str0ngPass!23"}, format="json")
        token = response.json()["token"]
        self.assertNotEqual(token, self.token.key)
        self.assertEqual(self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 200)

    def test_signing_in_restarts_the_lifetime_of_a_live_token(self):
        """Signing in on day 89 must not leave a session that dies the next day, nor sign other devices out."""
        Token.objects.filter(pk=self.token.pk).update(created=timezone.now() - timezone.timedelta(days=89))
        response = self.client.post(LOGIN_URL, {"phone": self.user.phone, "password": "Str0ngPass!23"}, format="json")
        self.assertEqual(response.json()["token"], self.token.key)
        self.assertAlmostEqual(
            Token.objects.get(pk=self.token.pk).created, timezone.now(), delta=timezone.timedelta(minutes=1)
        )
