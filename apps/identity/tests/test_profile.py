"""The signed-in user: reading `/me/`, editing it, and signing out."""

from rest_framework.authtoken.models import Token

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import User
from apps.identity.tests.base import (
    LOGOUT_URL,
    ME_URL,
)


class MeAndLogoutTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
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
