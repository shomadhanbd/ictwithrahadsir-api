"""The student profile and the `/me` payload."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academic.models import ClassLevel, Group
from apps.core.testing import bearer
from apps.profiles.models import GuardianProfile, StudentProfile

User = get_user_model()


class GuardianProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="01810001111", name="Student")
        self.student = StudentProfile.objects.create(user=self.user)

    def test_the_phone_is_stored_canonically(self):
        guardian = GuardianProfile.objects.create(student=self.student, phone="+8801910001111")
        self.assertEqual(guardian.phone, "01910001111")

    def test_a_blank_phone_stays_blank_rather_than_null(self):
        guardian = GuardianProfile.objects.create(student=self.student)
        self.assertEqual(guardian.phone, "")

    def test_it_is_reached_from_the_student_as_guardian(self):
        guardian = GuardianProfile.objects.create(student=self.student, name="Karim")
        self.student.refresh_from_db()
        self.assertEqual(self.student.guardian, guardian)


class StudentPayloadTests(TestCase):
    """Guardian fields are read through the student profile."""

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

    def test_the_guardian_reads_through_the_relation(self):
        student = StudentProfile.objects.create(user=self.user, institution="Dhaka College")
        GuardianProfile.objects.create(student=student, name="Karim", phone="01911002233")

        block = self._me()["student"]

        self.assertEqual(set(block), self.STUDENT_KEYS)
        self.assertEqual(block["guardian_name"], "Karim")
        self.assertEqual(block["guardian_phone"], "01911002233")

    def test_a_student_with_no_guardian_row_reads_as_blank(self):
        """A student without a profile row still gets a payload."""
        StudentProfile.objects.create(user=self.user, institution="Dhaka College")

        block = self._me()["student"]

        self.assertEqual(set(block), self.STUDENT_KEYS)
        self.assertEqual(block["guardian_name"], "")
        self.assertEqual(block["guardian_phone"], "")

    def test_writing_the_block_creates_the_guardian_row(self):
        response = self.client.post(
            self.url,
            {"student": {"guardian_name": "Karim", "guardian_phone": "01911002233"}},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        guardian = GuardianProfile.objects.get(student__user=self.user)
        self.assertEqual(guardian.name, "Karim")
        self.assertEqual(guardian.phone, "01911002233")

    def test_me_carries_the_class_and_group(self):
        hsc, science = ClassLevel.objects.create(name="HSC"), Group.objects.create(name="Science")
        student = StudentProfile.objects.create(user=self.user, class_level=hsc, group=science)
        GuardianProfile.objects.create(student=student)

        block = self._me()["student"]
        self.assertEqual((block["class_level_id"], block["group_id"]), (hsc.pk, science.pk))

    def test_a_student_sets_their_own_class_and_group(self):
        hsc, science = ClassLevel.objects.create(name="HSC"), Group.objects.create(name="Science")
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
        science = Group.objects.create(name="Science")
        response = self.client.post(
            self.url, {"student": {"group_id": science.pk}}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)
