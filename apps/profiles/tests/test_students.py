"""The student profile and the `/me` payload."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academic.models import ClassLevel, Group
from apps.core.testing import bearer, next_slug
from apps.profiles.models import StudentProfile

User = get_user_model()


class GuardianFieldsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="01810001111", name="Student")

    def test_the_phone_is_stored_canonically(self):
        student = StudentProfile.objects.create(user=self.user, guardian_phone="+8801910001111")
        self.assertEqual(student.guardian_phone, "01910001111")

    def test_a_blank_phone_stays_blank_rather_than_null(self):
        self.assertEqual(StudentProfile.objects.create(user=self.user).guardian_phone, "")


class StudentPayloadTests(TestCase):
    #: What `/me` emits and nothing more. Widening this is a frontend change.
    STUDENT_KEYS = {
        "guardian_name",
        "guardian_phone",
        "institution",
        "educational_session",
        "address",
        "class_level_id",
        "group_id",
    }

    def setUp(self):
        self.user = User.objects.create_user(phone="01810002222", name="Student", password="Str0ngPass!23")
        self.auth = bearer(self.user)
        self.url = reverse("api:identity:current_user")

    def _me(self):
        response = self.client.get(self.url, **self.auth)
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def test_a_user_with_no_student_row_reads_as_null(self):
        self.assertIsNone(self._me()["student"])

    def test_the_guardian_is_part_of_the_block(self):
        StudentProfile.objects.create(
            user=self.user, institution="Dhaka College", guardian_name="Karim", guardian_phone="01911002233"
        )

        block = self._me()["student"]

        self.assertEqual(set(block), self.STUDENT_KEYS)
        self.assertEqual(block["guardian_name"], "Karim")
        self.assertEqual(block["guardian_phone"], "01911002233")

    def test_a_student_with_no_guardian_reads_as_blank(self):
        StudentProfile.objects.create(user=self.user, institution="Dhaka College")

        block = self._me()["student"]

        self.assertEqual(set(block), self.STUDENT_KEYS)
        self.assertEqual(block["guardian_name"], "")
        self.assertEqual(block["guardian_phone"], "")

    def test_writing_the_block_saves_the_guardian(self):
        response = self.client.post(
            self.url,
            {"student": {"guardian_name": "Karim", "guardian_phone": "01911002233"}},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        student = StudentProfile.objects.get(user=self.user)
        self.assertEqual((student.guardian_name, student.guardian_phone), ("Karim", "01911002233"))

    def test_me_carries_the_class_and_group(self):
        hsc, science = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="Science"),
        )
        StudentProfile.objects.create(user=self.user, class_level=hsc, group=science)

        block = self._me()["student"]
        self.assertEqual((block["class_level_id"], block["group_id"]), (hsc.pk, science.pk))

    def test_a_student_sets_their_own_class_and_group(self):
        hsc, science = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="Science"),
        )
        response = self.client.post(
            self.url,
            {"student": {"class_level_id": hsc.pk, "group_id": science.pk}},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertEqual((profile.class_level_id, profile.group_id), (hsc.pk, science.pk))

    def test_a_group_needs_a_class(self):
        science = Group.objects.create(slug=next_slug("group"), name="Science")
        response = self.client.post(
            self.url, {"student": {"group_id": science.pk}}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)

    def test_a_common_group_is_not_a_students_own(self):
        hsc, general = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="General", is_common=True),
        )
        response = self.client.post(
            self.url,
            {"student": {"class_level_id": hsc.pk, "group_id": general.pk}},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("group_id", str(response.content))

    def test_clearing_the_class_clears_the_group(self):
        hsc, science = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="Science"),
        )
        StudentProfile.objects.create(user=self.user, class_level=hsc, group=science)

        response = self.client.post(
            self.url, {"student": {"class_level_id": None}}, content_type="application/json", **self.auth
        )

        self.assertEqual(response.status_code, 200, response.content)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertEqual((profile.class_level_id, profile.group_id), (None, None))

    def test_a_group_alone_is_checked_against_the_saved_class(self):
        hsc, science = (
            ClassLevel.objects.create(slug=next_slug("classlevel"), name="HSC"),
            Group.objects.create(slug=next_slug("group"), name="Science"),
        )
        StudentProfile.objects.create(user=self.user, class_level=hsc)

        response = self.client.post(
            self.url, {"student": {"group_id": science.pk}}, content_type="application/json", **self.auth
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(StudentProfile.objects.get(user=self.user).group_id, science.pk)

    def test_a_student_cannot_pick_a_retired_class(self):
        retired = ClassLevel.objects.create(slug=next_slug("classlevel"), name="Old SSC", is_active=False)
        response = self.client.post(
            self.url, {"student": {"class_level_id": retired.pk}}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)
