import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import openpyxl
from rest_framework.authtoken.models import Token

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import OTP, User
from apps.identity.tests.base import LOGIN_URL

IMPORT_URL = reverse("api:identity:admin_user_import")

STANDARD_HEADER = ["name", "phone", "email", "password", "institution"]
PASSWORD = "Str0ngPass!23"


def workbook(header, rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)

    buffer = io.BytesIO()
    book.save(buffer)
    return SimpleUploadedFile(
        "students.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class UserImportTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            phone="01899000001", name="Admin", password=PASSWORD, role=User.Role.ADMIN
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=self.admin).key}"}

    def upload(self, header, rows):
        return self.client.put(IMPORT_URL, {"file": workbook(header, rows)}, format="multipart", **self.auth)

    def test_a_full_row_becomes_an_account_that_can_sign_in(self):
        response = self.upload(
            STANDARD_HEADER, [("Nusrat Jahan", "01855000001", "n@example.com", PASSWORD, "Dhaka College")]
        )

        self.assertEqual(response.json()["created"], 1)
        user = User.objects.get(phone="01855000001")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.student.institution, "Dhaka College")
        self.assertEqual(self.client.post(LOGIN_URL, {"phone": "01855000001", "password": PASSWORD}).status_code, 200)

    def test_importing_issues_no_otp(self):
        self.upload(STANDARD_HEADER, [("Nusrat Jahan", "01855000001", "", PASSWORD, "")])
        self.assertFalse(OTP.objects.exists())

    def test_each_way_a_row_can_be_rejected_is_reported(self):
        response = self.upload(
            STANDARD_HEADER,
            [
                ("Good One", "01855000001", "g1@example.com", PASSWORD, "Dhaka College"),
                ("No Password", "01855000002", "g2@example.com", "", ""),
                ("Weak Password", "01855000003", "g3@example.com", "123456", ""),
                ("", "01855000004", "g4@example.com", PASSWORD, ""),
                ("Bad Phone", "12345", "g5@example.com", PASSWORD, ""),
            ],
        )

        self.assertEqual(
            response.json(),
            {
                "created": 1,
                "skipped": 4,
                "skipped_reasons": {
                    "missing_password": 1,
                    "weak_password": 1,
                    "missing_name": 1,
                    "invalid_phone": 1,
                },
            },
        )
        self.assertEqual(User.objects.filter(phone__startswith="01855").count(), 1)

    def test_a_number_already_on_file_is_reported_as_such(self):
        User.objects.create_user(phone="01855000001", name="Existing", password=PASSWORD)

        response = self.upload(STANDARD_HEADER, [("Duplicate", "01855000001", "", PASSWORD, "")])

        self.assertEqual(response.json()["skipped_reasons"], {"already_on_file": 1})

    def test_the_panels_own_export_spelling_is_accepted(self):
        """Export writes `user_name`/`user_phone`/`user_email`, so a sheet
        exported from the roster can be filled in and sent straight back."""
        response = self.upload(
            ["user_name", "user_phone", "user_email", "password", "institution"],
            [("Exported Back", "01855000010", "e@example.com", PASSWORD, "Notre Dame")],
        )

        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(User.objects.get(phone="01855000010").student.institution, "Notre Dame")

    def test_a_respelt_phone_is_stored_canonically(self):
        self.upload(STANDARD_HEADER, [("Country Code", "+8801855000001", "", PASSWORD, "")])
        self.assertTrue(User.objects.filter(phone="01855000001").exists())
