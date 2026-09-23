"""The student/guardian split, and the payload it must not change."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.academic.models import ClassLevel, Group
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
    """`guardian_name`/`guardian_phone` now cross a join to reach the payload.

    Both frontends read them flat inside `student`, and `/me` is a frozen
    contract, so splitting the model must not split the response.
    """

    #: What `/me` emits and nothing more. Widening this is a frontend change.
    STUDENT_KEYS = {
        "guardian_name",
        "guardian_phone",
        "institution",
        "educational_session",
        "address",
    }

    def setUp(self):
        self.user = User.objects.create_user(phone="01810002222", name="Student", password="Str0ngPass!23")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.user).key}"}
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
        """The row should always exist -- but a student created before the
        split, or straight from the ORM, has none, and the payload must not
        raise `RelatedObjectDoesNotExist` over it."""
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

    def test_the_public_block_carries_no_academic_placement(self):
        """Class and group are the admin roster's business. Adding them to
        `/me` would widen a payload nobody asked to change."""
        student = StudentProfile.objects.create(
            user=self.user,
            class_level=ClassLevel.objects.create(name="HSC"),
            group=Group.objects.create(name="Science"),
        )
        GuardianProfile.objects.create(student=student)

        self.assertEqual(set(self._me()["student"]), self.STUDENT_KEYS)
