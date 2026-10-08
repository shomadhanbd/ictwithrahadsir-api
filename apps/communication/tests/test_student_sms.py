from unittest import mock

from django.urls import reverse

from rest_framework.test import APITestCase

from apps.communication.models import SmsMessage
from apps.communication.services import send_sms
from apps.core.testing import bearer, make_user
from apps.identity.models import User
from apps.profiles.models import StudentProfile


class StudentSmsTests(APITestCase):
    def setUp(self):
        self.admin = make_user(role=User.Role.ADMIN, name="Office")
        self.auth = bearer(self.admin)
        self.student = make_user(phone="01810001111")
        self.url = reverse("api:communication:student_sms", args=[self.student.pk])

    def send(self, auth=None, **body):
        with mock.patch("apps.communication.services.get_gateway") as gateway:
            response = self.client.post(self.url, body, format="json", **(auth or self.auth))
        return response, gateway.return_value.send

    def test_staff_text_a_student_and_it_is_logged(self):
        response, sent = self.send(to="student", message="Class moved to 5pm.")
        self.assertEqual(response.status_code, 201, response.content)
        sent.assert_called_once_with("01810001111", "Class moved to 5pm.")
        record = SmsMessage.objects.get()
        self.assertEqual((record.purpose, record.recipient, record.sent_by), ("custom", self.student, self.admin))
        self.assertEqual(response.json()["sent_by"], {"id": self.admin.id, "name": "Office"})

    def test_a_guardian_message_goes_to_the_guardian_phone(self):
        StudentProfile.objects.update_or_create(user=self.student, defaults={"guardian_phone": "01710002222"})
        response, sent = self.send(to="guardian", message="Fees are due.")
        self.assertEqual(response.status_code, 201, response.content)
        sent.assert_called_once_with("01710002222", "Fees are due.")
        self.assertEqual(response.json()["to"], "guardian")

    def test_a_guardian_message_needs_a_guardian_phone(self):
        response, sent = self.send(to="guardian", message="Fees are due.")
        self.assertEqual(response.status_code, 422)
        self.assertIn("to", response.json()["errors"])
        sent.assert_not_called()

    def test_a_message_has_a_length_limit(self):
        response, _ = self.send(to="student", message="x" * 481)
        self.assertEqual(response.status_code, 422)

    def test_only_admins_send_texts(self):
        response, sent = self.send(auth=bearer(make_user(role=User.Role.MODERATOR)), to="student", message="Hi")
        self.assertEqual(response.status_code, 403)
        sent.assert_not_called()

    def test_the_history_lists_only_that_students_messages(self):
        with mock.patch("apps.communication.services.get_gateway"):
            send_sms("01810001111", "Yours", purpose=SmsMessage.Purpose.CUSTOM, recipient=self.student)
            send_sms("01910009999", "Someone else's", purpose=SmsMessage.Purpose.CUSTOM, recipient=make_user())
            send_sms("01810001111", "123456", purpose=SmsMessage.Purpose.PHONE_VERIFY, recipient=self.student)
        rows = self.client.get(self.url, **self.auth).json()["data"]
        self.assertEqual([row["body"] for row in rows], ["", "Yours"])
