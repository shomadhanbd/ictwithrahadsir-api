from apps.core.testing import make_user
from apps.courses.models import Course, Enrollment
from apps.identity.models import User
from apps.profiles.models import TeacherProfile
from apps.website.tests.base import HOME_URL, WebsiteTestCase


class HomeTests(WebsiteTestCase):
    def setUp(self):
        super().setUp()
        self.course = Course.objects.create(title="ICT", slug="ict-home", status="published", is_featured=True)
        Course.objects.create(title="Hidden", slug="hidden-home", status="published")
        TeacherProfile.objects.create(user=make_user(role=User.Role.TEACHER, name="Rahad Sir"))

    def test_home_lists_featured_courses_and_teachers(self):
        body = self.client.get(HOME_URL).json()
        self.assertEqual(list(body), ["courses", "banners", "testimonials", "stats", "instructors"])
        self.assertEqual([c["title"] for c in body["courses"]], ["ICT"])
        self.assertEqual([t["name"] for t in body["instructors"]], ["Rahad Sir"])

    def test_the_numbers_are_counted_and_zeros_left_out(self):
        Enrollment.objects.create(course=self.course, user=make_user())
        stats = self.client.get(HOME_URL).json()["stats"]
        self.assertEqual(
            stats,
            [
                {"label": "প্রিমিয়াম কোর্স", "value": "2"},
                {"label": "সন্তুষ্ট শিক্ষার্থী", "value": "1"},
                {"label": "দক্ষ শিক্ষক", "value": "1"},
            ],
        )

    def test_a_typed_number_wins_over_the_count(self):
        items = [{"metric": "students", "label": "শিক্ষার্থী", "value": "৫০০০+"}]
        self.patch("home.stats", {"content": {"items": items}})
        self.assertEqual(self.client.get(HOME_URL).json()["stats"], [{"label": "শিক্ষার্থী", "value": "৫০০০+"}])

    def test_hidden_numbers_are_not_sent(self):
        self.patch("home.stats", {"is_visible": False})
        self.assertEqual(self.client.get(HOME_URL).json()["stats"], [])
