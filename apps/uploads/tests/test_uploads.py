import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from PIL import Image
from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.identity.models import User

URL = reverse('api:uploads:upload')


def image_bytes(fmt="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format=fmt)
    return buffer.getvalue()


PDF = b"%PDF-1.4\n%demo\n"


class UploadTests(APITestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media, API_BASE_URL="https://api.example.test")
        override.enable()
        self.addCleanup(override.disable)
        self.admin = bearer(make_user(role=User.Role.ADMIN))

    def upload(self, content, name, kind="image", auth=None):
        file = SimpleUploadedFile(name, content)
        return self.client.post(
            URL, {"file": file, "kind": kind}, format="multipart", **(self.admin if auth is None else auth)
        )

    def stored(self, link):
        return Path(self.media) / link.split("/media/", 1)[1]

    def test_an_image_is_stored_and_its_link_returned(self):
        response = self.upload(image_bytes(), "cover.png")
        self.assertEqual(response.status_code, 201, response.content)
        link = response.json()["link"]
        self.assertTrue(link.startswith("https://api.example.test/media/uploads/image/"))
        self.assertTrue(link.endswith(".png"))
        self.assertTrue(self.stored(link).exists())

    def test_the_extension_comes_from_the_content_not_the_name(self):
        link = self.upload(image_bytes("JPEG"), "photo.png").json()["link"]
        self.assertTrue(link.endswith(".jpg"))

    def test_a_pdf_is_stored(self):
        response = self.upload(PDF, "syllabus.pdf", kind="pdf")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["link"].endswith(".pdf"))

    def test_a_file_that_is_not_what_it_claims_is_refused(self):
        self.assertEqual(self.upload(b"not really an image", "fake.png").status_code, 422)
        self.assertEqual(self.upload(image_bytes(), "fake.pdf", kind="pdf").status_code, 422)

    def test_the_back_office_reads_upload_errors_in_english(self):
        response = self.upload(b"not really an image", "fake.png")
        self.assertEqual(response.json()["errors"]["file"], ["That file is not an image we can read."])

    def test_svg_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertEqual(self.upload(svg, "logo.svg").status_code, 422)

    def test_an_oversized_file_is_refused(self):
        with patch("apps.uploads.validators.MAX_IMAGE_BYTES", 10):
            response = self.upload(image_bytes(), "big.png")
        self.assertEqual(response.status_code, 422)
        self.assertIn("file", response.json()["errors"])

    def test_an_unknown_kind_is_refused(self):
        self.assertEqual(self.upload(PDF, "x.exe", kind="program").status_code, 422)

    def test_every_back_office_role_may_upload(self):
        for role in (User.Role.MODERATOR, User.Role.TEACHER):
            response = self.upload(image_bytes(), "a.png", auth=bearer(make_user(role=role)))
            self.assertEqual(response.status_code, 201, role)

    def test_students_and_visitors_may_not(self):
        self.assertEqual(self.upload(image_bytes(), "a.png", auth=bearer(make_user())).status_code, 403)
        self.assertEqual(self.upload(image_bytes(), "a.png", auth={}).status_code, 401)
