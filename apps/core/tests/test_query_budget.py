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

from apps.assessment.models import Exam, Question, QuestionBank
from apps.billing.models import Order
from apps.content.models import Notice, NoticeCategory
from apps.courses.models import (
    Content,
    Course,
    CourseCategory,
    CoursePrice,
    Enrollment,
    Routine,
    Section,
)
from apps.faculty.models import CourseInstructor, Teacher
from apps.identity.models import User


class QueryBudgetTests(APITestCase):
    """Builds one realistic dataset and asserts a ceiling per endpoint."""

    # Overridden by the scaled subclass. Nothing below reads these except
    # the fixture builder, so the assertions are identical at both sizes.
    COURSES = 12
    SECTIONS_PER_COURSE = 6
    CONTENTS_PER_SECTION = 5
    CATEGORY_ROOTS = 3
    CATEGORY_CHILDREN = 3
    NOTICES = 20
    QUESTIONS = 30
    PRACTICE_BANKS = 6

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(phone="01810000001", name="Student")
        cls.token = Token.objects.create(user=cls.user)

        roots = [
            CourseCategory.objects.create(title=f"Category {i}")
            for i in range(cls.CATEGORY_ROOTS)
        ]
        for root in roots:
            for j in range(cls.CATEGORY_CHILDREN):
                # A third level, so a tree walk that only handles two is caught.
                child = CourseCategory.objects.create(
                    title=f"{root.title} child {j}", category=root
                )
                CourseCategory.objects.create(
                    title=f"{child.title} leaf", category=child
                )

        teachers = [Teacher.objects.create(name=f"Teacher {i}") for i in range(3)]

        cls.courses = []
        for i in range(cls.COURSES):
            course = Course.objects.create(title=f"Course {i}", active=True, featured=True)
            course.categories.set(roots)
            cls.courses.append(course)

            CourseInstructor.objects.create(
                course=course, teacher=teachers[i % 3], name=f"Teacher {i % 3}"
            )
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
                child = Section.objects.create(
                    course=course, section=parent, title=f"C{i} Sub {s}"
                )
                for c in range(cls.CONTENTS_PER_SECTION):
                    for target in (parent, child):
                        Content.objects.create(
                            course=course,
                            section=target,
                            title=f"C{i}S{s}-{target.id}-{c}",
                            type=Content.Type.VIDEO if c % 2 else Content.Type.PDF,
                        )

        cls.detail_course = cls.courses[0]

        # The exam hangs off the last course, not the one the detail test
        # reads, so that test's content counts stay exactly the fixture's.
        exam_course = cls.courses[-1]
        bank = QuestionBank.objects.create(title="Bank")
        for i in range(cls.QUESTIONS):
            Question.objects.create(bank=bank, question=f"Q{i}", answer="a")
        exam_content = Content.objects.create(
            course=exam_course,
            section=Section.objects.filter(course=exam_course).first(),
            title="Exam content",
            type=Content.Type.EXAM,
        )
        cls.exam = Exam.objects.create(content=exam_content, question_bank=bank)

        # A nested folder tree for the practice topic list. Each folder is a
        # child of the one before it, so the tree gets *deeper* as the fixture
        # grows -- which is what an implementation that walks the tree per
        # folder is worst at.
        parent = None
        for i in range(cls.PRACTICE_BANKS):
            parent = QuestionBank.objects.create(title=f"Practice {i}", parent=parent)
            Question.objects.create(bank=parent, question=f"PQ{i}", answer="a")

        notice_category = NoticeCategory.objects.create(title="Notice cat")
        for i in range(cls.NOTICES):
            Notice.objects.create(title=f"Notice {i}").categories.add(notice_category)

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    # -- course list --------------------------------------------------------

    def test_public_course_list(self):
        with self.assertNumQueries(9):
            response = self.client.get("/api/v1/courses/?per_page=12")
        self.assertEqual(len(response.data["data"]), 12)

    def test_public_course_list_authenticated(self):
        self.authenticate()
        with self.assertNumQueries(12):
            response = self.client.get("/api/v1/courses/?per_page=12")
        self.assertEqual(len(response.data["data"]), 12)

    def test_my_courses(self):
        self.authenticate()
        with self.assertNumQueries(11):
            response = self.client.get("/api/v1/me/courses/")
        self.assertEqual(len(response.data["data"]), self.COURSES)

    # -- course detail ------------------------------------------------------

    def test_course_detail(self):
        """Was 38 queries: two per section, recursively, plus six COUNTs."""
        with self.assertNumQueries(10):
            response = self.client.get(f"/api/v1/courses/{self.detail_course.slug}/")
        self.assertEqual(len(response.data["sections"]), self.SECTIONS_PER_COURSE)
        # The tree still resolves, not just cheaply but correctly.
        first = response.data["sections"][0]
        self.assertEqual(len(first["sub_sections"]), 1)
        self.assertEqual(len(first["contents"]), self.CONTENTS_PER_SECTION)
        self.assertEqual(
            len(first["sub_sections"][0]["contents"]), self.CONTENTS_PER_SECTION
        )

    # -- categories ---------------------------------------------------------

    def test_course_category_list(self):
        """Was one query per node in the tree, at any depth."""
        with self.assertNumQueries(4):
            response = self.client.get("/api/v1/course-categories/")
        self.assertEqual(len(response.data["data"]), self.CATEGORY_ROOTS)
        children = response.data["data"][0]["children"]
        self.assertEqual(len(children), self.CATEGORY_CHILDREN)
        self.assertEqual(len(children[0]["children"]), 1)

    # -- homepage -----------------------------------------------------------

    def test_home(self):
        with self.assertNumQueries(17):
            response = self.client.get("/api/v1/home/")
        self.assertEqual(len(response.data["courses"]), 12)

    # -- notices ------------------------------------------------------------

    def test_notice_list(self):
        """Was one query per notice, for the m2m category ids."""
        with self.assertNumQueries(3):
            response = self.client.get("/api/v1/notices/?per_page=20")
        self.assertEqual(len(response.data["data"]), 20)

    # -- exam ---------------------------------------------------------------

    def test_exam_detail(self):
        self.authenticate()
        with self.assertNumQueries(6):
            response = self.client.get(f"/api/v1/exams/{self.exam.pk}/")
        questions = response.data["question"]["body"]["sections"][0]["questions"]
        self.assertEqual(len(questions), self.QUESTIONS)

    def test_exam_submission_marks_in_one_query_per_paper(self):
        """Was one SELECT per submitted answer."""
        self.authenticate()
        payload = {
            "sections": [
                {
                    "answers": [
                        {"mcq_id": q.id, "user_answer": "a"}
                        # This exam's own bank, not every question in the
                        # database -- which is what a real submission sends,
                        # and keeps the expected mark tied to the fixture.
                        for q in Question.objects.filter(
                            bank=self.exam.question_bank
                        )
                    ]
                }
            ],
            "duration": 60,
        }
        # 8, not 6: the two added statements are a SAVEPOINT/RELEASE pair, not
        # data queries. The INSERT runs inside its own atomic block so that a
        # duplicate submission arriving at the same moment raises a catchable
        # IntegrityError instead of a 500 (see apps.assessment.services).
        # What this test exists to pin is unchanged -- the answer keys are
        # still fetched in ONE query for the whole paper, not one per answer,
        # which is what ScaledQueryBudgetTests re-proves at twice the size.
        with self.assertNumQueries(8):
            response = self.client.post(
                f"/api/v1/exams/{self.exam.pk}/submission/", payload, format="json"
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(float(response.data["marks"]), float(self.QUESTIONS))

    def test_exam_ranking_does_not_scale_with_attempt_count(self):
        """Was: load every attempt id into Python to find one index."""
        others = [
            User.objects.create_user(phone=f"018200000{i:02d}", name=f"S{i}")
            for i in range(10)
        ]
        from apps.assessment.models import ExamAttempt

        for i, other in enumerate(others):
            ExamAttempt.objects.create(exam=self.exam, user=other, marks=i, duration=10)
        ExamAttempt.objects.create(exam=self.exam, user=self.user, marks=5, duration=10)

        self.authenticate()
        with self.assertNumQueries(5):
            response = self.client.get(f"/api/v1/exams/{self.exam.pk}/ranking/")
        # Four attempts scored above 5 (marks 6-9), so the caller sits fifth.
        # The attempt on the same marks and duration ties rather than
        # displacing them, which the old index-of-a-materialised-list
        # approach decided arbitrarily.
        self.assertEqual(response.data["user_rank"], 5)

    # -- admin lists --------------------------------------------------------

    def test_admin_content_list(self):
        """The flat `exam_*` keys are read off a related row per content."""
        admin = User.objects.create_user(
            phone="01899999999", name="Admin", role=User.Role.ADMIN
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}"
        )
        with self.assertNumQueries(3):
            response = self.client.get("/api/v1/admin/contents/?per_page=50")
        self.assertEqual(len(response.data["data"]), 50)


    def test_practice_topics_do_not_scale_with_folder_count(self):
        """Was: one tree walk plus one COUNT per folder in the bank.

        `all_questions()` costs a query per level of nesting, so listing the
        topics cost more the deeper and wider the bank grew -- the one thing
        a topic list is guaranteed to do over time.
        """
        with self.assertNumQueries(2):
            response = self.client.get("/api/v1/practice/topics/")
        self.assertEqual(response.status_code, 200)
        # Every seeded practice folder holds a question, and each also
        # inherits its descendants', so all of them are playable.
        self.assertEqual(len(response.data["data"]), self.PRACTICE_BANKS + 1)


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
    QUESTIONS = 60
    PRACTICE_BANKS = 12
