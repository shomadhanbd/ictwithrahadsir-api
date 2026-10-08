"""Query-count guards for the read-heavy endpoints."""

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.billing.models import Payment, Product
from apps.communication.models import Notice, NoticeCategory
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import (
    Content,
    Course,
    CourseTeacher,
    Enrollment,
    Routine,
    Section,
)
from apps.identity.models import User
from apps.profiles.models import TeacherProfile


class QueryBudgetTests(APITestCase):
    """Builds one realistic dataset and asserts a ceiling per endpoint."""

    # Overridden by ScaledQueryBudgetTests; only the fixture builder reads these.
    COURSES = 12
    SECTIONS_PER_COURSE = 6
    CONTENTS_PER_SECTION = 5
    NOTICES = 20

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(phone="01810000001", name="Student")
        cls.token = Token.objects.create(user=cls.user)

        teachers = [
            TeacherProfile.objects.create(
                user=User.objects.create_user(phone=f"0187700{i:04d}", name=f"Teacher {i}", role=User.Role.TEACHER)
            ).user
            for i in range(3)
        ]

        cls.courses = []
        for i in range(cls.COURSES):
            course = Course.objects.create(
                slug=next_slug("course"), title=f"Course {i}", status='published', is_featured=True
            )
            cls.courses.append(course)

            CourseTeacher.objects.create(course=course, user=teachers[i % 3])
            Routine.objects.create(course=course, title=f"Routine {i}")
            Enrollment.objects.create(course=course, user=cls.user)
            product = Product.objects.create(
                product_id=next_slug("product"), title=f"Bundle {i}", price=1000, base_price=1000
            )
            product.courses.add(course)
            Payment.objects.create(user=cls.user, product=product, amount=1000, status=Payment.Status.VALID)

            for s in range(cls.SECTIONS_PER_COURSE):
                parent = Section.objects.create(course=course, title=f"C{i} Section {s}")
                # One nested level, so the recursive serializer is exercised.
                child = Section.objects.create(course=course, section=parent, title=f"C{i} Sub {s}")
                for c in range(cls.CONTENTS_PER_SECTION):
                    for target in (parent, child):
                        Content.objects.create(
                            course=course,
                            section=target,
                            title=f"C{i}S{s}-{target.id}-{c}",
                            type=Content.Type.VIDEO if c % 2 else Content.Type.PDF,
                        )

        cls.detail_course = cls.courses[0]

        notice_category = NoticeCategory.objects.create(slug=next_slug("noticecategory"), title="Notice cat")
        for i in range(cls.NOTICES):
            Notice.objects.create(slug=next_slug("notice"), title=f"Notice {i}").categories.add(notice_category)

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

    def test_public_course_list(self):
        with self.assertNumQueries(6):
            response = self.client.get("/api/public/courses/?per_page=12")
        self.assertEqual(len(response.data["data"]), 12)

    def test_public_course_list_authenticated(self):
        self.authenticate()
        # Includes one read of the student profile per request.
        with self.assertNumQueries(10):
            response = self.client.get("/api/public/courses/?per_page=12")
        self.assertEqual(len(response.data["data"]), 12)

    def test_my_courses(self):
        self.authenticate()
        # One is the student profile, read once to offer only the packages meant for them.
        with self.assertNumQueries(9):
            response = self.client.get("/api/public/me/courses/")
        self.assertEqual(len(response.data["data"]), self.COURSES)

    def test_course_detail(self):
        with self.assertNumQueries(8):
            response = self.client.get(f"/api/public/courses/{self.detail_course.slug}/")
        self.assertEqual(len(response.data["curriculum"]), self.SECTIONS_PER_COURSE)
        # The tree still resolves, not just cheaply but correctly.
        first = response.data["curriculum"][0]
        self.assertEqual(len(first["sub_sections"]), 1)
        self.assertEqual(len(first["contents"]), self.CONTENTS_PER_SECTION)
        self.assertEqual(len(first["sub_sections"][0]["contents"]), self.CONTENTS_PER_SECTION)

    def test_home(self):
        with self.assertNumQueries(10):
            response = self.client.get("/api/public/home/")
        self.assertEqual(len(response.data["courses"]), 12)

    def test_notice_list(self):
        """Count, page, then categories, class levels and batches each prefetched once."""
        with self.assertNumQueries(5):
            response = self.client.get("/api/public/notices/?per_page=20")
        self.assertEqual(len(response.data["data"]), 20)

    def test_admin_content_list(self):
        """Each lesson's exam and question count are joined, not fetched per row."""
        admin = make_user(role=User.Role.ADMIN)
        self.client.credentials(**bearer(admin))
        with self.assertNumQueries(4):
            response = self.client.get("/api/private/contents/?per_page=50")
        self.assertEqual(len(response.data["data"]), 50)


class ScaledQueryBudgetTests(QueryBudgetTests):
    """The same assertions against twice the data."""

    COURSES = 24
    SECTIONS_PER_COURSE = 12
    CONTENTS_PER_SECTION = 10
    NOTICES = 40
