import socket
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from rest_framework.exceptions import NotFound
from rest_framework.test import APITestCase

from apps.core.streaming import stream_file
from apps.core.testing import bearer, make_user
from apps.courses.models import Content, Course, CourseTeacher, Section
from apps.identity.models import User

PUBLIC_IP = "93.184.216.34"


def resolves_to(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return mock.patch("socket.getaddrinfo", return_value=[(family, socket.SOCK_STREAM, 6, "", (address, 80))])


def upstream(status=200, content_type="application/pdf"):
    response = mock.Mock(status_code=status, headers={"Content-Type": content_type, "Content-Length": "4"})
    response.iter_content.return_value = iter([b"%PDF"])
    return response


@override_settings(STREAM_ALLOW_PRIVATE_HOSTS=False)
class StreamGuardTests(SimpleTestCase):
    def stream(self, url):
        return stream_file(url, filename="x.pdf", content_type="application/pdf")

    def test_private_and_odd_addresses_are_never_fetched(self):
        cases = [
            ("http://127.0.0.1:8000/api/public/home/", "127.0.0.1"),
            ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
            ("http://10.0.0.5/file.pdf", "10.0.0.5"),
            ("http://[::1]/file.pdf", "::1"),
            ("http://[::ffff:127.0.0.1]/file.pdf", "::ffff:127.0.0.1"),
            ("http://intranet.example/file.pdf", "192.168.1.10"),
        ]
        for url, address in cases:
            with self.subTest(url=url), resolves_to(address), mock.patch("requests.Session.get") as get:
                with self.assertRaises(NotFound):
                    self.stream(url)
                get.assert_not_called()

    def test_non_http_schemes_are_refused(self):
        with mock.patch("requests.Session.get") as get:
            for url in ("file:///etc/passwd", "ftp://example.com/a.pdf", "gopher://x"):
                with self.subTest(url=url), self.assertRaises(NotFound):
                    self.stream(url)
            get.assert_not_called()

    def test_a_public_host_is_fetched_without_following_redirects(self):
        with resolves_to(PUBLIC_IP), mock.patch("requests.Session.get", return_value=upstream()) as get:
            response = self.stream("https://files.example.com/a.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIs(get.call_args.kwargs["allow_redirects"], False)

    def test_a_redirect_is_refused(self):
        with (
            resolves_to(PUBLIC_IP),
            mock.patch("requests.Session.get", return_value=upstream(status=302)),
            self.assertRaises(NotFound),
        ):
            self.stream("https://files.example.com/a.pdf")

    def test_the_connection_goes_to_the_address_that_was_checked(self):
        """DNS rebinding: a second lookup could answer 169.254.169.254, so there is no second lookup."""
        with resolves_to(PUBLIC_IP), mock.patch("requests.Session.get", return_value=upstream()) as get:
            self.stream("https://files.example.com:8443/a.pdf")
        self.assertEqual(get.call_args.args[0], f"https://{PUBLIC_IP}:8443/a.pdf")
        self.assertEqual(get.call_args.kwargs["headers"]["Host"], "files.example.com:8443")

    def test_a_file_declared_too_large_is_refused(self):
        big = upstream()
        big.headers["Content-Length"] = str(200 * 1024 * 1024 + 1)
        with resolves_to(PUBLIC_IP), mock.patch("requests.Session.get", return_value=big), self.assertRaises(NotFound):
            self.stream("https://files.example.com/a.pdf")
        big.close.assert_called_once()

    def test_a_body_past_the_size_cap_is_cut_off(self):
        endless = upstream()
        endless.headers.pop("Content-Length")
        endless.iter_content.return_value = iter([b"x" * 10] * 100)
        with (
            resolves_to(PUBLIC_IP),
            mock.patch("requests.Session.get", return_value=endless),
            mock.patch("apps.core.streaming.MAX_BYTES", 25),
        ):
            body = b"".join(self.stream("https://files.example.com/a.pdf").streaming_content)
        self.assertEqual(body, b"x" * 20)
        endless.close.assert_called_once()

    def test_a_slow_drip_is_cut_off_at_the_total_deadline(self):
        drip = upstream()
        drip.iter_content.return_value = iter([b"a", b"b", b"c"])
        clock = iter([0, 1, 1000, 2000])
        with (
            resolves_to(PUBLIC_IP),
            mock.patch("requests.Session.get", return_value=drip),
            mock.patch("apps.core.streaming.time.monotonic", side_effect=lambda: next(clock)),
        ):
            body = b"".join(self.stream("https://files.example.com/a.pdf").streaming_content)
        self.assertEqual(body, b"a")

    def test_the_content_type_is_forced(self):
        with (
            resolves_to(PUBLIC_IP),
            mock.patch("requests.Session.get", return_value=upstream(content_type="text/html")),
        ):
            response = self.stream("https://files.example.com/a.pdf")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")


@override_settings(STREAM_ALLOW_PRIVATE_HOSTS=False)
class LessonPdfAddressTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title="ICT", slug="ict-pdf", status="published")
        self.section = Section.objects.create(course=self.course, title="Ch 1", slug="ict-pdf-ch1")
        self.teacher = make_user(role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, user=self.teacher)

    def test_an_internal_address_is_not_streamed(self):
        lesson = Content.objects.create(
            course=self.course,
            section=self.section,
            title="Sheet",
            slug="ict-pdf-sheet",
            type="pdf",
            paid=False,
            pdf_file="http://127.0.0.1:8000/api/public/home/",
        )
        with resolves_to("127.0.0.1"), mock.patch("requests.Session.get") as get:
            response = self.client.get(reverse("api:courses:content_pdf", args=[lesson.slug]))
        self.assertEqual(response.status_code, 404)
        get.assert_not_called()

    def test_an_internal_address_is_refused_when_saved(self):
        body = {
            "course_id": self.course.pk,
            "section_id": self.section.pk,
            "title": "Sheet",
            "type": "pdf",
            "pdf_file": "http://169.254.169.254/latest/meta-data/",
        }
        with resolves_to("169.254.169.254"):
            response = self.client.post("/api/private/contents/", body, format="json", **bearer(self.teacher))
        self.assertEqual(response.status_code, 422)
        self.assertIn("pdf_file", response.json()["errors"])
