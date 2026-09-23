"""The teacher roster: one screen writing an account and its profile."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.academic.models import ClassLevel, Group, Subject
from apps.profiles.models import TeacherProfile

User = get_user_model()

LIST_URL = reverse("api:profiles:admin-teacher-list")
LOOKUP_URL = reverse("api:profiles:admin_teacher_lookup")


class TeacherRosterTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone="01700001111", name="Admin", password="Str0ngPass!23", role=User.Role.ADMIN
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=admin).key}"}

        self.teacher_user = User.objects.create_user(phone="01710001111", name="Rahad Sir", role=User.Role.TEACHER)
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, designation="Founder")

    def test_the_roster_lists_teachers(self):
        body = self.client.get(LIST_URL, **self.auth).json()
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["name"], "Rahad Sir")

    def test_search_matches_the_account_name(self):
        """The name lives on the `User`, so `search_fields` has to cross the
        join -- without that `?search=` is accepted and silently ignored."""
        TeacherProfile.objects.create(
            user=User.objects.create_user(phone="01710002222", name="Karim", role=User.Role.TEACHER)
        )

        body = self.client.get(LIST_URL, {"search": "Rahad"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["name"], "Rahad Sir")

    def test_the_lookup_is_unpaginated_and_wrapped_in_data(self):
        """The panel renders this straight into a dropdown."""
        body = self.client.get(LOOKUP_URL, **self.auth).json()
        self.assertEqual(list(body.keys()), ["data"])
        self.assertEqual(len(body["data"]), 1)

    def test_the_roster_is_admin_only(self):
        student = User.objects.create_user(phone="01810003333", name="Student")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=student).key}"}
        self.assertEqual(self.client.get(LIST_URL, **auth).status_code, 403)


class TeacherWriteTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone="01700001111", name="Admin", password="Str0ngPass!23", role=User.Role.ADMIN
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=admin).key}"}
        self.hsc = ClassLevel.objects.create(name="HSC")
        # A subject is one row per level and group, so it needs both.
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=Group.objects.create(name="Science"))

    def _post(self, **overrides):
        payload = {"name": "New Teacher", "phone": "01710004444", **overrides}
        return self.client.post(LIST_URL, payload, content_type="application/json", **self.auth)

    def test_creating_a_teacher_creates_their_account(self):
        response = self._post(email="new@example.com", designation="Senior Teacher")

        self.assertEqual(response.status_code, 201)
        profile = TeacherProfile.objects.get(user__phone="01710004444")
        self.assertEqual(profile.user.name, "New Teacher")
        self.assertEqual(profile.designation, "Senior Teacher")

    def test_a_new_teacher_lands_in_the_teacher_group(self):
        """A roster entry means nothing until the account holds the role the
        permission tier reads."""
        self._post()
        self.assertEqual(User.objects.get(phone="01710004444").role, User.Role.TEACHER)

    def test_a_new_account_needs_a_phone(self):
        """`user_id` alone is enough to link an existing account, so the
        account fields cannot be required outright."""
        response = self.client.post(LIST_URL, {"name": "Nameless"}, content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_subjects_and_classes_round_trip(self):
        response = self._post(subject_ids=[self.ict.pk], level_ids=[self.hsc.pk])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["subject_ids"], [self.ict.pk])
        profile = TeacherProfile.objects.get(user__phone="01710004444")
        self.assertEqual(list(profile.levels.values_list("name", flat=True)), ["HSC"])

    def test_one_account_cannot_hold_two_roster_entries(self):
        """A declared `PrimaryKeyRelatedField` does not inherit the OneToOne's
        validator, so without an explicit one this reaches the database."""
        existing = User.objects.create_user(phone="01710005555", name="Taken", role=User.Role.TEACHER)
        TeacherProfile.objects.create(user=existing)

        response = self.client.post(LIST_URL, {"user_id": existing.pk}, content_type="application/json", **self.auth)

        self.assertEqual(response.status_code, 422)
        self.assertIn("user_id", response.json()["errors"])

    def test_naming_an_admin_as_a_teacher_does_not_demote_them(self):
        """`set_role` makes its argument the *only* role."""
        admin = User.objects.create_user(phone="01700009999", name="Boss", role=User.Role.ADMIN)

        response = self.client.post(LIST_URL, {"user_id": admin.pk}, content_type="application/json", **self.auth)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(pk=admin.pk).role, User.Role.ADMIN)

    def test_a_teacher_without_a_password_cannot_sign_in(self):
        """`has_usable_password()` only looks for the "!" prefix, so a row
        written directly carries an empty string that reads as usable."""
        user = User.objects.create_user(phone="01710006666", name="No Login", role=User.Role.TEACHER)
        TeacherProfile.objects.create(user=user)
        User.objects.filter(pk=user.pk).update(password="")

        body = self.client.get(LIST_URL, {"search": "No Login"}, **self.auth).json()

        self.assertFalse(body["data"][0]["can_sign_in"])

    def test_a_teacher_with_a_password_can_sign_in(self):
        user = User.objects.create_user(
            phone="01710007777", name="Has Login", password="Str0ngPass!23", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=user)

        body = self.client.get(LIST_URL, {"search": "Has Login"}, **self.auth).json()

        self.assertTrue(body["data"][0]["can_sign_in"])

    def test_the_public_key_list_is_not_widened_by_the_admin_one(self):
        """`AdminTeacherSerializer` adds keys; `TeacherSerializer` must not."""
        from apps.profiles.api.private.serializers import TeacherSerializer

        self.assertEqual(
            TeacherSerializer.Meta.fields,
            ["id", "name", "designation", "description", "type", "order", "image"],
        )
