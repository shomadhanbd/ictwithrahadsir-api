"""Only a superuser changes a superuser's account, on every path that writes one."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.identity.models import User
from apps.profiles.models import TeacherProfile


class SuperuserAccountTests(APITestCase):
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

    def test_the_teachers_api_refuses_to_edit_a_linked_superuser(self):
        profile = TeacherProfile.objects.create(user=self.root)
        url = reverse("api:profiles:admin_teacher_detail", args=[profile.pk])
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

    def test_the_teachers_api_refuses_to_delete_a_linked_superuser(self):
        profile = TeacherProfile.objects.create(user=self.root)
        url = reverse("api:profiles:admin_teacher_detail", args=[profile.pk])
        self.assertEqual(self.client.delete(url, **self.admin_auth).status_code, 403)
        self.assertTrue(TeacherProfile.objects.filter(pk=profile.pk).exists())
        self.assertEqual(User.objects.get(pk=self.root.pk).role, User.Role.ADMIN)

    def test_the_django_teacher_admin_refuses_to_delete_too(self):
        request = RequestFactory().post("/")
        request.user = make_user(role=User.Role.ADMIN)
        profile_admin = admin.site._registry[TeacherProfile]
        profile = TeacherProfile.objects.create(user=self.root)
        with self.assertRaises(PermissionDenied):
            profile_admin.delete_model(request, profile)
        with self.assertRaises(PermissionDenied):
            profile_admin.delete_queryset(request, TeacherProfile.objects.all())
        self.assertTrue(TeacherProfile.objects.filter(pk=profile.pk).exists())


class UserAdminEscalationTests(TestCase):
    """An admin-role account manages users but cannot make itself, or anyone, a superuser."""

    def setUp(self):
        self.user_admin = admin.site._registry[User]
        self.admin = make_user(role=User.Role.ADMIN)
        self.superuser = User.objects.create_superuser(phone="01700000010", password="Str0ngPass!23", name="Root")

    def request(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_only_a_superuser_can_grant_superuser(self):
        self.assertIn("is_superuser", self.user_admin.get_readonly_fields(self.request(self.admin), self.admin))
        self.assertIn("user_permissions", self.user_admin.get_readonly_fields(self.request(self.admin), self.admin))
        self.assertNotIn("is_superuser", self.user_admin.get_readonly_fields(self.request(self.superuser), self.admin))

    def test_an_admin_cannot_edit_or_delete_a_superuser(self):
        request = self.request(self.admin)
        self.assertFalse(self.user_admin.has_change_permission(request, self.superuser))
        self.assertFalse(self.user_admin.has_delete_permission(request, self.superuser))
        self.assertTrue(self.user_admin.has_change_permission(request, make_user()))
