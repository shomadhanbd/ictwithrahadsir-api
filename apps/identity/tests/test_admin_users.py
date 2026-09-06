"""`/admin/users/` -- the roster screen, and who is allowed to change it."""

from django.urls import reverse
from django.utils import timezone

from rest_framework.authtoken.models import Token

from apps.billing.models import Order
from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import User
from apps.identity.tests.base import (
    ADMIN_USER_SEARCH_URL,
    ADMIN_USER_URL,
)


class AdminRoleEscalationTests(ThrottledAPITestCase):
    """IsAdminRole admits instructors, so /admin/users must not let them hand
    out privileged roles or edit privileged accounts.

    These answer 403, not 422: the request is well formed, the caller is just
    not allowed to make it. The rules live in
    `apps.identity.api.v1.permissions.CanManageUsers` -- they used to be in
    the serializer, which meant they only ran on create and update and DELETE
    went through unchecked (see AdminUserDeletionTests).
    """

    def setUp(self):
        super().setUp()
        self.instructor = User.objects.create_user(
            phone="01710000009", name="Instructor", password="Str0ngPass!23",
            role=User.Role.INSTRUCTOR,
        )
        self.auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.instructor).key}"
        }
        self.admin = User.objects.create_user(
            phone="01710000010", name="Admin", password="Str0ngPass!23",
            role=User.Role.ADMIN, is_staff=True,
        )

    def test_instructor_cannot_create_an_admin(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Backdoor", "phone": "01810001234", "role": "admin"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(phone="01810001234").exists())

    def test_instructor_cannot_promote_themselves(self):
        response = self.client.patch(
            reverse('api:identity:v1:admin-user-detail', args=[self.instructor.pk]),
            {"role": "admin"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.instructor.refresh_from_db()
        self.assertEqual(self.instructor.role, User.Role.INSTRUCTOR)

    def test_instructor_cannot_reset_an_admins_password(self):
        response = self.client.patch(
            reverse('api:identity:v1:admin-user-detail', args=[self.admin.pk]),
            {"password": "Tak30v3r!pass"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("Str0ngPass!23"))

    def test_admin_can_still_create_an_admin(self):
        admin_auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"
        }
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Second Admin", "phone": "01810004321", "role": "admin"},
            **admin_auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_instructor_can_still_manage_students(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "A Student", "phone": "01810005678", "role": "student"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_instructor_cannot_block_a_student(self):
        """`is_active` is the block switch, so writing it is the same act as
        DELETE by another route and needs the same rank."""
        student = User.objects.create_user(phone="01810007001", name="Student")
        response = self.client.patch(
            reverse('api:identity:v1:admin-user-detail', args=[student.pk]),
            {"is_active": False},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        student.refresh_from_db()
        self.assertTrue(student.is_active)

class AdminUserDeletionTests(ThrottledAPITestCase):
    """DELETE /admin/users/<pk>/.

    Two separate problems used to meet here. The escalation guards lived in
    the serializer, and `destroy()` never builds one -- so an instructor could
    delete an admin outright. And the delete was a real delete, against a
    schema where `Order`, `Payment`, `Enrollment`, `ExamAttempt` and
    `ContentCompletion` all cascade off `user`: removing a student erased
    what they had paid and what they had scored.
    """

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            phone="01710000021", name="Admin", password="Str0ngPass!23",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.admin_auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"
        }
        self.instructor = User.objects.create_user(
            phone="01710000022", name="Instructor", password="Str0ngPass!23",
            role=User.Role.INSTRUCTOR,
        )
        self.instructor_auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.instructor).key}"
        }
        self.student = User.objects.create_user(
            phone="01810007777", name="Student", password="Str0ngPass!23"
        )

    def _delete(self, target, auth):
        return self.client.delete(
            reverse('api:identity:v1:admin-user-detail', args=[target.pk]), **auth
        )

    def test_instructor_cannot_delete_an_admin(self):
        self.assertEqual(self._delete(self.admin, self.instructor_auth).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_instructor_cannot_delete_a_student(self):
        """Cutting off a paying student's access is an admin decision even
        when it is the instructor's own student."""
        self.assertEqual(self._delete(self.student, self.instructor_auth).status_code, 403)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_admin_delete_deactivates_and_keeps_the_payment_record(self):
        order = Order.objects.create(user=self.student, amount=500, total=500)

        self.assertEqual(self._delete(self.student, self.admin_auth).status_code, 204)

        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_delete_revokes_the_accounts_tokens(self):
        key = Token.objects.create(user=self.student).key
        self._delete(self.student, self.admin_auth)
        self.assertFalse(Token.objects.filter(key=key).exists())

    def test_a_deactivated_account_drops_out_of_the_default_listing(self):
        """The panel refetches the list after a delete, so this is what makes
        the row appear to be gone."""
        self._delete(self.student, self.admin_auth)

        listed = self.client.get(ADMIN_USER_URL, **self.admin_auth).json()["data"]
        self.assertNotIn(self.student.pk, [row["id"] for row in listed])

        found = self.client.get(
            ADMIN_USER_URL, {"status": "inactive"}, **self.admin_auth
        ).json()["data"]
        self.assertEqual([row["id"] for row in found], [self.student.pk])

    def test_an_admin_can_restore_a_deactivated_account(self):
        self._delete(self.student, self.admin_auth)
        response = self.client.patch(
            reverse('api:identity:v1:admin-user-detail', args=[self.student.pk]),
            {"is_active": True},
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

class AdminUserTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            phone="01710000001", name="Admin", password="Str0ngPass!23",
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"
        }
        self.student = User.objects.create_user(
            phone="01810005555", name="Rahim Uddin", password="Str0ngPass!23"
        )

    def test_admin_endpoints_reject_students(self):
        student_auth = {
            "HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.student).key}"
        }
        self.assertEqual(self.client.get(ADMIN_USER_URL, **student_auth).status_code, 403)

    def test_admin_user_list_is_paginated(self):
        response = self.client.get(ADMIN_USER_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("meta", body)
        self.assertEqual(body["meta"]["total"], 2)

    def test_admin_user_list_filters_by_role(self):
        response = self.client.get(ADMIN_USER_URL, {"role": "student"}, **self.auth)
        self.assertEqual(response.json()["meta"]["total"], 1)

    def test_role_all_means_every_role(self):
        """`all` is the admin panel's "no filter" option, not a role.

        The dropdown defaults to it and the page sends it on every request,
        so matching it literally returned nothing and the Users screen was
        empty until a specific role was chosen.
        """
        response = self.client.get(ADMIN_USER_URL, {"role": "all"}, **self.auth)
        self.assertEqual(response.json()["meta"]["total"], 2)

    def test_role_all_is_the_same_as_omitting_the_filter(self):
        with_param = self.client.get(ADMIN_USER_URL, {"role": "all"}, **self.auth)
        without = self.client.get(ADMIN_USER_URL, **self.auth)
        self.assertEqual(
            [row["id"] for row in with_param.json()["data"]],
            [row["id"] for row in without.json()["data"]],
        )

    def test_role_all_still_combines_with_search(self):
        """The page sends role and search together; "any role" must not
        quietly widen the result back out to everyone."""
        response = self.client.get(
            ADMIN_USER_URL, {"role": "all", "search": "Rahim"}, **self.auth
        )
        body = response.json()
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["name"], "Rahim Uddin")

    def test_a_real_role_is_still_filtered(self):
        """The sentinel must not turn into "ignore the role parameter"."""
        response = self.client.get(ADMIN_USER_URL, {"role": "admin"}, **self.auth)
        body = response.json()
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["role"], "admin")

    def test_admin_user_search(self):
        response = self.client.get(
            ADMIN_USER_SEARCH_URL, {"search": "Rahim"}, **self.auth
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Rahim Uddin")

    def test_an_abandoned_registration_stays_off_the_roster(self):
        """`/auth/otp/verify/` has to create a row to own the token it
        returns, so every abandoned sign-up used to leave a permanent
        nameless "student" in this list and in the dashboard count."""
        User.objects.create_unverified("01810009999")

        body = self.client.get(ADMIN_USER_URL, **self.auth).json()
        self.assertEqual(body["meta"]["total"], 2)
        self.assertNotIn("01810009999", [row["phone"] for row in body["data"]])

    def test_completing_registration_puts_them_on_the_roster(self):
        user = User.objects.create_unverified("01810009998")
        self.assertEqual(User.objects.students().count(), 1)

        user.registered_at = timezone.now()
        user.name = "Finished"
        user.save()

        self.assertEqual(User.objects.students().count(), 2)
        body = self.client.get(ADMIN_USER_URL, **self.auth).json()
        self.assertIn("01810009998", [row["phone"] for row in body["data"]])

    def test_admin_can_create_a_user(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {
                "name": "Created", "phone": "01810006666",
                "password": "Str0ngPass!23", "role": "student",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(phone="01810006666")
        self.assertTrue(created.check_password("Str0ngPass!23"))
