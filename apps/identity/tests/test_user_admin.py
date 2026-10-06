from django.contrib import admin
from django.test import RequestFactory, TestCase

from apps.core.testing import make_user
from apps.identity.models import User


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
