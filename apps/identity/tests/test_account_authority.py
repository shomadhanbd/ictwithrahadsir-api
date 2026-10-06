"""One rule, on every path that writes an account: only a superuser changes a superuser's account."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from apps.core.testing import bearer, make_user
from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import User
from apps.profiles.models import TeacherProfile

TEACHERS_URL = reverse("api:profiles:admin-teacher-list")


class SuperuserAccountTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.root = User.objects.create_superuser(phone="01700000020", password="Str0ngPass!23", name="Root")
        self.admin_auth = bearer(make_user(role=User.Role.ADMIN))
        self.root_auth = bearer(self.root)

    def assert_root_phone_unchanged(self):
        self.assertEqual(User.objects.get(pk=self.root.pk).phone, "01700000020")

    def test_the_user_api_refuses_an_admin(self):
        url = reverse("api:identity:admin_user_detail", args=[self.root.pk])
        response = self.client.patch(url, {"phone": "01710009090"}, format="json", **self.admin_auth)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.delete(url, **self.admin_auth).status_code, 403)
        self.assert_root_phone_unchanged()

    def test_the_teachers_api_refuses_to_link_a_superuser(self):
        response = self.client.post(TEACHERS_URL, {"user_id": self.root.pk}, format="json", **self.admin_auth)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TeacherProfile.objects.exists())

    def test_the_teachers_api_refuses_to_edit_a_linked_superuser(self):
        profile = TeacherProfile.objects.create(user=self.root)
        url = reverse("api:profiles:admin-teacher-detail", args=[profile.pk])
        response = self.client.patch(url, {"phone": "01710009091"}, format="json", **self.admin_auth)
        self.assertEqual(response.status_code, 403)
        self.assert_root_phone_unchanged()

    def test_a_superuser_still_manages_their_own_account(self):
        url = reverse("api:identity:admin_user_detail", args=[self.root.pk])
        response = self.client.patch(url, {"name": "Root 2"}, format="json", **self.root_auth)
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_django_teacher_admin_refuses_too(self):
        request = RequestFactory().post("/")
        request.user = make_user(role=User.Role.ADMIN)
        profile_admin = admin.site._registry[TeacherProfile]
        with self.assertRaises(PermissionDenied):
            profile_admin.save_model(request, TeacherProfile(user=self.root), form=None, change=False)
        self.assertFalse(TeacherProfile.objects.exists())
