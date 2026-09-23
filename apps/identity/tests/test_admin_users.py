from unittest import mock

from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.billing.models import Order
from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP, User
from apps.identity.tests.base import (
    ADMIN_USER_SEARCH_URL,
    ADMIN_USER_URL,
    LOGIN_URL,
)
from apps.profiles.models import StudentProfile


class AdminRoleEscalationTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user(
            phone="01710000009",
            name="Teacher",
            password="Str0ngPass!23",
            role=User.Role.TEACHER,
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.teacher).key}"}
        self.admin = User.objects.create_user(
            phone="01710000010",
            name="Admin",
            password="Str0ngPass!23",
            role=User.Role.ADMIN,
            is_staff=True,
        )

    def test_teacher_cannot_create_an_admin(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Backdoor", "phone": "01810001234", "role": "admin"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(phone="01810001234").exists())

    def test_teacher_cannot_promote_themselves(self):
        response = self.client.patch(
            reverse('api:identity:admin_user_detail', args=[self.teacher.pk]),
            {"role": "admin"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, User.Role.TEACHER)

    def test_teacher_cannot_create_a_moderator(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Desk", "phone": "01810001235", "role": "moderator"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(phone="01810001235").exists())

    def test_teacher_cannot_reset_a_moderators_password(self):
        moderator = User.objects.create_user(
            phone="01710000011",
            name="Moderator",
            password="Str0ngPass!23",
            role=User.Role.MODERATOR,
        )
        response = self.client.patch(
            reverse('api:identity:admin_user_detail', args=[moderator.pk]),
            {"password": "Tak30v3r!pass"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        moderator.refresh_from_db()
        self.assertTrue(moderator.check_password("Str0ngPass!23"))

    def test_teacher_cannot_reset_an_admins_password(self):
        response = self.client.patch(
            reverse('api:identity:admin_user_detail', args=[self.admin.pk]),
            {"password": "Tak30v3r!pass"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("Str0ngPass!23"))

    def test_admin_can_still_create_an_admin(self):
        admin_auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"}
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Second Admin", "phone": "01810004321", "role": "admin", "password": "Str0ngPass!23"},
            **admin_auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_teacher_can_still_manage_students(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "A Student", "phone": "01810005678", "role": "student", "password": "Str0ngPass!23"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_teacher_cannot_block_a_student(self):
        student = User.objects.create_user(phone="01810007001", name="Student")
        response = self.client.patch(
            reverse('api:identity:admin_user_detail', args=[student.pk]),
            {"is_active": False},
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        student.refresh_from_db()
        self.assertTrue(student.is_active)


class AdminUserDeletionTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            phone="01710000021",
            name="Admin",
            password="Str0ngPass!23",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.admin_auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"}
        self.teacher = User.objects.create_user(
            phone="01710000022",
            name="Teacher",
            password="Str0ngPass!23",
            role=User.Role.TEACHER,
        )
        self.teacher_auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.teacher).key}"}
        self.student = User.objects.create_user(phone="01810007777", name="Student", password="Str0ngPass!23")

    def _delete(self, target, auth):
        return self.client.delete(reverse('api:identity:admin_user_detail', args=[target.pk]), **auth)

    def test_teacher_cannot_delete_an_admin(self):
        self.assertEqual(self._delete(self.admin, self.teacher_auth).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_teacher_cannot_delete_a_student(self):
        self.assertEqual(self._delete(self.student, self.teacher_auth).status_code, 403)
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
        self._delete(self.student, self.admin_auth)

        listed = self.client.get(ADMIN_USER_URL, **self.admin_auth).json()["data"]
        self.assertNotIn(self.student.pk, [row["id"] for row in listed])

        found = self.client.get(ADMIN_USER_URL, {"status": "inactive"}, **self.admin_auth).json()["data"]
        self.assertEqual([row["id"] for row in found], [self.student.pk])

    def test_an_admin_can_restore_a_deactivated_account(self):
        self._delete(self.student, self.admin_auth)
        response = self.client.patch(
            reverse('api:identity:admin_user_detail', args=[self.student.pk]),
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
            phone="01710000001",
            name="Admin",
            password="Str0ngPass!23",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"}
        self.student = User.objects.create_user(phone="01810005555", name="Rahim Uddin", password="Str0ngPass!23")

    def test_the_roster_lists_every_role(self):
        """The Users page is the whole registered roster, not the students.

        Teachers went missing from it once, because they were seeded with
        `is_active=False` to mean "roster entry, does not sign in" -- the same
        flag `deactivate_user` sets, and the list defaults to active only.
        """
        for phone, name, role in [
            ("01710009001", "Teacher", User.Role.TEACHER),
            ("01710009002", "Moderator", User.Role.MODERATOR),
        ]:
            User.objects.create_user(phone=phone, name=name, role=role)

        body = self.client.get(ADMIN_USER_URL, **self.auth).json()
        roles = {row["role"] for row in body["data"]}

        self.assertEqual(roles, {"admin", "moderator", "teacher", "student"})

    def test_admin_endpoints_reject_students(self):
        student_auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.student).key}"}
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
        response = self.client.get(ADMIN_USER_URL, {"role": "all", "search": "Rahim"}, **self.auth)
        body = response.json()
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["name"], "Rahim Uddin")

    def test_a_real_role_is_still_filtered(self):
        response = self.client.get(ADMIN_USER_URL, {"role": "admin"}, **self.auth)
        body = response.json()
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["role"], "admin")

    def test_admin_user_search(self):
        response = self.client.get(ADMIN_USER_SEARCH_URL, {"search": "Rahim"}, **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Rahim Uddin")

    def test_admin_user_search_returns_only_picker_fields(self):
        response = self.client.get(ADMIN_USER_SEARCH_URL, {"search": "Rahim"}, **self.auth)
        self.assertEqual(set(response.json()["data"][0]), {"id", "name", "phone", "email"})

    def test_a_duplicate_email_in_another_case_is_422_not_500(self):
        User.objects.create_user(phone="01977000111", email="casetest@example.com", name="First")

        response = self.client.post(
            ADMIN_USER_URL,
            {
                "name": "Dup",
                "phone": "01977000222",
                "email": "CASETEST@Example.COM",
                "role": "student",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("email", response.json()["errors"])
        self.assertFalse(User.objects.filter(phone="01977000222").exists())

    def test_a_blank_email_is_accepted_and_stored_as_null(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {
                "name": "No Email",
                "phone": "01977000444",
                "email": "",
                "role": "student",
                "password": "Str0ngPass!23",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(User.objects.get(phone="01977000444").email)

    def test_the_phone_cannot_be_cleared(self):
        """The phone is the only login identifier and the column is NOT NULL.

        There is no longer an "either/or" with the email to fall back on.
        """
        target = User.objects.create_user(phone="01977000555", email="keeps@example.com", name="Both")
        response = self.client.patch(
            reverse("api:identity:admin_user_detail", args=[target.pk]),
            {"phone": None},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        target.refresh_from_db()
        self.assertEqual(target.phone, "01977000555")

    def test_creating_an_account_without_a_phone_is_refused(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {"name": "Email Only", "email": "emailonly@example.com", "role": "student"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_an_abandoned_registration_stays_off_the_roster(self):
        User.objects.create_unverified("01810009999")

        body = self.client.get(ADMIN_USER_URL, **self.auth).json()
        self.assertEqual(body["meta"]["total"], 2)
        self.assertNotIn("01810009999", [row["phone"] for row in body["data"]])

    def test_completing_registration_puts_them_on_the_roster(self):
        user = User.objects.create_unverified("01810009998")
        self.assertEqual(User.objects.students().count(), 1)

        user.name = "Finished"
        user.set_password("Str0ngPass!23")
        user.save()

        self.assertEqual(User.objects.students().count(), 2)
        body = self.client.get(ADMIN_USER_URL, **self.auth).json()
        self.assertIn("01810009998", [row["phone"] for row in body["data"]])

    def test_updating_the_student_block_is_reflected_in_the_response(self):
        """The response must show the new values, not the cached ones.

        The user is fetched with `select_related("student")`, so the profile
        row is already cached by the time it is written to.
        """
        target = User.objects.create_user(phone="01977000777", name="Student")
        StudentProfile.objects.create(user=target, institution="Old College")

        response = self.client.patch(
            reverse("api:identity:admin_user_detail", args=[target.pk]),
            {"student": {"institution": "New College"}},
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["student"]["institution"], "New College")
        self.assertEqual(StudentProfile.objects.get(user=target).institution, "New College")

    def test_creating_an_account_without_a_password_is_refused(self):
        """No OTP is issued on this path, so the password is the only way in.

        An account made without one could not sign in at all until it went
        through the login-code flow to set one.
        """
        for password in ({}, {"password": ""}):
            with self.subTest(password=password):
                response = self.client.post(
                    ADMIN_USER_URL,
                    {"name": "No Pass", "phone": "01812340100", "role": "student", **password},
                    **self.auth,
                )
                self.assertEqual(response.status_code, 422)
                self.assertIn("password", response.json()["errors"])
                self.assertFalse(User.objects.filter(phone="01812340100").exists())

    def test_editing_an_account_does_not_require_a_password(self):
        target = User.objects.create_user(phone="01812340101", name="Existing", password="Str0ngPass!23")

        response = self.client.patch(
            reverse("api:identity:admin_user_detail", args=[target.pk]),
            {"name": "Renamed"},
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.name, "Renamed")
        self.assertTrue(target.check_password("Str0ngPass!23"))

    def test_creating_a_student_sends_no_otp(self):
        """An OTP proves a stranger holds the number they typed in. An admin
        entering a student on their behalf has already vouched for it, so no
        code is issued and no SMS is paid for."""
        with mock.patch("apps.identity.services.get_sms_backend") as sms:
            response = self.client.post(
                ADMIN_USER_URL,
                {
                    "name": "Admin Made",
                    "phone": "01812340000",
                    "role": "student",
                    "password": "Str0ngPass!23",
                },
                **self.auth,
            )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(OTP.objects.filter(phone="01812340000").exists())
        sms.assert_not_called()

    def test_an_admin_made_student_can_sign_in_without_verifying(self):
        """The account is usable the moment it is made: no OTP stands between
        the student and their first login."""
        self.client.post(
            ADMIN_USER_URL,
            {"name": "Admin Made", "phone": "01812340000", "role": "student", "password": "Str0ngPass!23"},
            **self.auth,
        )

        response = self.client.post(LOGIN_URL, {"phone": "01812340000", "password": "Str0ngPass!23"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])

    def test_the_whole_student_block_round_trips(self):
        """The roster's block, which carries the academic placement too.

        `/me` and the login response deliberately do not: those go through
        `StudentProfileSerializer`, whose key list both frontends read.
        """
        target = User.objects.create_user(phone="01977000999", name="Student")
        block = {
            "guardian_name": "Abdul Karim",
            "guardian_phone": "01911002233",
            "institution": "Dhaka College",
            "educational_session": "2025-26",
            "address": "House 42, Road 7, Banani, Dhaka 1213",
        }

        response = self.client.patch(
            reverse("api:identity:admin_user_detail", args=[target.pk]),
            {"student": block},
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["student"], {**block, "class_level_id": None, "group_id": None})
        profile = StudentProfile.objects.get(user=target)
        self.assertEqual(profile.address, "House 42, Road 7, Banani, Dhaka 1213")
        self.assertEqual(profile.guardian.name, "Abdul Karim")

    def test_a_user_without_a_profile_serializes_student_as_null(self):
        target = User.objects.create_user(phone="01977000888", name="Teacher", role=User.Role.TEACHER)

        response = self.client.get(reverse("api:identity:admin_user_detail", args=[target.pk]), **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["student"])

    def test_creating_an_account_without_a_name_is_refused(self):
        """It would be indistinguishable from an abandoned sign-up, and
        `registered()` would keep it off the roster."""
        response = self.client.post(
            ADMIN_USER_URL,
            {"phone": "01810006677", "role": "student"},
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("name", response.json()["errors"])
        self.assertFalse(User.objects.filter(phone="01810006677").exists())

    def test_admin_can_create_a_user(self):
        response = self.client.post(
            ADMIN_USER_URL,
            {
                "name": "Created",
                "phone": "01810006666",
                "password": "Str0ngPass!23",
                "role": "student",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(phone="01810006666")
        self.assertTrue(created.check_password("Str0ngPass!23"))
