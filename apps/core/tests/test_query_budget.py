"""Query-count guards for the read-heavy endpoints.

Every endpoint here was once linear in the size of what it returned: one or
more extra queries per course, per section, per category, per notice. That
never shows up in a functional test -- the response is correct either way --
so it is pinned separately, by counting queries.

The point is not the absolute numbers, it is that they do not move when the
data grows. `ScaledQueryBudgetTests` re-runs the whole suite against a
dataset twice the size and asserts the *same* ceilings, which is what turns
"this is fast enough on my laptop" into "this does not degrade in
production". A change that makes an endpoint per-row again fails there even
if it happens to fit the ceiling at the smaller size.

Raising a number should be a deliberate decision with a reason, not a reflex
to make a failing build green.
"""

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.billing.models import Order
from apps.content.models import Notice, NoticeCategory
from apps.courses.models import (
    Content,
    Course,
    CourseCategory,
    CoursePrice,
    CourseTeacher,
    Enrollment,
    Routine,
    Section,
)
from apps.identity.models import User
from apps.profiles.models import TeacherProfile


class QueryBudgetTests(APITestCase):
    """Builds one realistic dataset and asserts a ceiling per endpoint.

    Each course-shaped budget dropped by one when the teacher block moved
    to `courses.CourseTeacher`: the payload reads through the assignment's
    account and its roster entry, and `CourseQuerySet._teacher_prefetch`
    joins both into the query that fetches the assignments rather than walking
    them as further prefetches.
    """

    # Overridden by the scaled subclass. Nothing below reads these except
    # the fixture builder, so the assertions are identical at both sizes.
    COURSES = 12
    SECTIONS_PER_COURSE = 6
    CONTENTS_PER_SECTION = 5
    CATEGORY_ROOTS = 3
    CATEGORY_CHILDREN = 3
    NOTICES = 20

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(phone="01810000001", name="Student")
        cls.token = Token.objects.create(user=cls.user)

        roots = [CourseCategory.objects.create(title=f"Category {i}") for i in range(cls.CATEGORY_ROOTS)]
        for root in roots:
            for j in range(cls.CATEGORY_CHILDREN):
                # A third level, so a tree walk that only handles two is caught.
                child = CourseCategory.objects.create(title=f"{root.title} child {j}", category=root)
                CourseCategory.objects.create(title=f"{child.title} leaf", category=child)

        teachers = [
            TeacherProfile.objects.create(
                user=User.objects.create_user(phone=f"0187700{i:04d}", name=f"Teacher {i}", role=User.Role.TEACHER)
            ).user
            for i in range(3)
        ]

        cls.courses = []
        for i in range(cls.COURSES):
            course = Course.objects.create(title=f"Course {i}", active=True, featured=True)
            course.categories.set(roots)
            cls.courses.append(course)

            CourseTeacher.objects.create(course=course, user=teachers[i % 3])
            Routine.objects.create(course=course, title=f"Routine {i}")
            CoursePrice.objects.create(
                priceable_type=CoursePrice.PRICEABLE_COURSE,
                priceable_id=course.id,
                title="Full",
                amount=1000,
            )
            Enrollment.objects.create(course=course, user=cls.user)
            Order.objects.create(user=cls.user, course=course, amount=1000, total=1000)

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

        notice_category = NoticeCategory.objects.create(title="Notice cat")
        for i in range(cls.NOTICES):
            Notice.objects.create(title=f"Notice {i}").categories.add(notice_category)

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

    # -- course list --------------------------------------------------------

    def test_public_course_list(self):
        with self.assertNumQueries(8):
            response = self.client.get("/api/public/courses/?per_page=12")
        self.assertEqual(len(response.data["data"]), 12)

    def test_public_course_list_authenticated(self):
        self.authenticate()
        with self.assertNumQueries(11):
            response = self.client.get("/api/public/courses/?per_page=12")
        self.assertEqual(len(response.data["data"]), 12)

    def test_my_courses(self):
        self.authenticate()
        with self.assertNumQueries(10):
            response = self.client.get("/api/public/me/courses/")
        self.assertEqual(len(response.data["data"]), self.COURSES)

    # -- course detail ------------------------------------------------------

    def test_course_detail(self):
        """Was 38 queries: two per section, recursively, plus six COUNTs."""
        with self.assertNumQueries(9):
            response = self.client.get(f"/api/public/courses/{self.detail_course.slug}/")
        self.assertEqual(len(response.data["sections"]), self.SECTIONS_PER_COURSE)
        # The tree still resolves, not just cheaply but correctly.
        first = response.data["sections"][0]
        self.assertEqual(len(first["sub_sections"]), 1)
        self.assertEqual(len(first["contents"]), self.CONTENTS_PER_SECTION)
        self.assertEqual(len(first["sub_sections"][0]["contents"]), self.CONTENTS_PER_SECTION)

    # -- categories ---------------------------------------------------------

    def test_course_category_list(self):
        """Was one query per node in the tree, at any depth."""
        with self.assertNumQueries(4):
            response = self.client.get("/api/public/course-categories/")
        self.assertEqual(len(response.data["data"]), self.CATEGORY_ROOTS)
        children = response.data["data"][0]["children"]
        self.assertEqual(len(children), self.CATEGORY_CHILDREN)
        self.assertEqual(len(children[0]["children"]), 1)

    # -- homepage -----------------------------------------------------------

    def test_home(self):
        with self.assertNumQueries(16):
            response = self.client.get("/api/public/home/")
        self.assertEqual(len(response.data["courses"]), 12)

    # -- notices ------------------------------------------------------------

    def test_notice_list(self):
        """Was one query per notice, for the m2m category ids."""
        with self.assertNumQueries(3):
            response = self.client.get("/api/public/notices/?per_page=20")
        self.assertEqual(len(response.data["data"]), 20)

    # -- exam ---------------------------------------------------------------

    def test_admin_content_list(self):
        """The flat `exam_*` keys are read off a related row per content.

        Four, not three: `role` is group membership now, so every
        authenticated request spends one query resolving the caller's role
        before any permission class can answer. It is a flat cost per
        request, not per row -- which is what `ScaledQueryBudgetTests`
        re-running this at twice the size proves.
        """
        admin = User.objects.create_user(phone="01899999999", name="Admin", role=User.Role.ADMIN)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {Token.objects.create(user=admin).key}")
        with self.assertNumQueries(4):
            response = self.client.get("/api/private/contents/?per_page=50")
        self.assertEqual(len(response.data["data"]), 50)


class ScaledQueryBudgetTests(QueryBudgetTests):
    """The same assertions against twice the data.

    Identical ceilings at both sizes is the actual property under test: it
    is what proves the endpoints are flat rather than merely fast enough at
    one particular fixture size.
    """

    COURSES = 24
    SECTIONS_PER_COURSE = 12
    CONTENTS_PER_SECTION = 10
    CATEGORY_ROOTS = 6
    CATEGORY_CHILDREN = 6
    NOTICES = 40
