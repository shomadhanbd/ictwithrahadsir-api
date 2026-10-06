from unittest import mock

from django.test import override_settings
from django.utils import timezone

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.academic.models import ClassLevel, Group
from apps.core.testing import next_slug
from apps.identity.models import User
from apps.identity.tests.base import (
    LOGIN_URL,
    LOGOUT_URL,
    ME_URL,
)
from apps.profiles.services import ensure_student_profile


class MeAndLogoutTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone="01810004444", name="Student", password="Str0ngPass!23")
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
        response = self.client.post(ME_URL, {"name": "Renamed"}, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Renamed")

    def test_logout_deletes_the_token(self):
        response = self.client.post(LOGOUT_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(Token.objects.filter(user=self.user).exists())


class PasswordChangeTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone="01810004445", name="Student", password="Str0ngPass!23")
        self.token = Token.objects.create(user=self.user)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token.key}"}

    def change(self, **body):
        return self.client.post(ME_URL, {"password": "N3wStr0ng!pass", **body}, format="json", **self.auth)

    def test_a_token_alone_cannot_set_a_new_password(self):
        for body in ({}, {"current_password": "wrong"}):
            with self.subTest(body=body):
                response = self.change(**body)
                self.assertEqual(response.status_code, 422)
                self.assertIn("current_password", response.json()["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ngPass!23"))

    def test_the_current_password_changes_it_and_signs_other_sessions_out(self):
        response = self.change(current_password="Str0ngPass!23")

        self.assertEqual(response.status_code, 200, response.content)
        new_token = response.json()["token"]
        self.assertNotEqual(new_token, self.token.key)
        self.assertEqual(self.client.get(ME_URL, **self.auth).status_code, 401)
        self.assertEqual(self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {new_token}").status_code, 200)

    def test_the_password_does_not_change_if_the_sessions_cannot_be_rotated(self):
        failing = mock.patch("apps.identity.api.public.views.issue_token", side_effect=RuntimeError("rotation failed"))
        with failing, self.assertLogs("django.request", level="ERROR"):
            response = self.change(current_password="Str0ngPass!23")
        self.assertEqual(response.status_code, 500)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ngPass!23"))

    def test_an_account_without_a_password_sets_its_first_one(self):
        self.user.set_unusable_password()
        self.user.save()
        self.assertEqual(self.change().status_code, 200)

    def test_other_profile_edits_need_no_password_and_keep_the_token(self):
        response = self.client.post(ME_URL, {"name": "Renamed"}, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token", response.json())


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


class StudentAudienceEditTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.hsc = ClassLevel.objects.create(name="HSC", slug="hsc-aud")
        self.science, self.arts = (
            Group.objects.create(slug=next_slug("group"), name="Science"),
            Group.objects.create(slug=next_slug("group"), name="Arts"),
        )
        self.user = User.objects.create_user(phone="01810004447", name="Student", password="Str0ngPass!23")
        ensure_student_profile(self.user, class_level=self.hsc, group=self.science)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.user).key}"}

    def test_a_student_changes_only_their_group(self):
        response = self.client.post(ME_URL, {"student": {"group_id": self.arts.pk}}, format="json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["student"]["group_id"], self.arts.pk)

    def test_a_group_without_any_class_is_still_refused(self):
        self.user.student.class_level = None
        self.user.student.group = None
        self.user.student.save()
        response = self.client.post(ME_URL, {"student": {"group_id": self.arts.pk}}, format="json", **self.auth)
        self.assertEqual(response.status_code, 422)
