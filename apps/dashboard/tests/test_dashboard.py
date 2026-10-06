from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.billing.models import Payment, Product
from apps.core.testing import bearer, make_user
from apps.courses.models import Course, CourseTeacher, Enrollment
from apps.identity.models import User

SUMMARY_URL = reverse("api:dashboard:admin_dashboard")
SALES_URL = reverse("api:dashboard:admin_dashboard_sales")
PAYMENTS_URL = reverse("api:dashboard:admin_dashboard_payments")


class DashboardTests(APITestCase):
    def setUp(self):
        self.auth = bearer(make_user(role=User.Role.ADMIN))
        self.student = make_user()
        course = Course.objects.create(title="ICT", slug="ict-dash")
        self.product = Product.objects.create(title="ICT", price=500, base_price=500)
        self.product.courses.add(course)
        self.now = timezone.now()

    def pay(self, amount, status=Payment.Status.VALID, when=None):
        return Payment.objects.create(
            user=self.student, product=self.product, amount=amount, status=status, transaction_date=when or self.now
        )

    def test_the_summary_counts_paid_income_orders_courses_and_students(self):
        self.pay(500)
        self.pay(300, when=self.now - timezone.timedelta(days=400))
        self.pay(999, status=Payment.Status.FAILED)
        self.pay(200, status=Payment.Status.INITIATED)

        body = self.client.get(SUMMARY_URL, **self.auth).json()

        self.assertEqual(body["income"]["lifeTime"], 800)
        self.assertEqual(body["income"]["thisMonth"], 500)
        self.assertEqual(body["orders"]["completed"]["thisMonth"], 1)
        self.assertEqual(body["orders"]["incomplete"]["thisMonth"], 1)
        self.assertEqual(body["totalCounts"], {"courses": 1, "students": 1})
        self.assertEqual(body["studentsRegistered"]["thisMonth"], 1)

    def test_sales_overview_covers_twelve_months_ending_now(self):
        self.pay(500)

        body = self.client.get(SALES_URL, **self.auth).json()

        self.assertEqual(len(body["months"]), 12)
        self.assertEqual(body["months"][-1], timezone.localtime(self.now).strftime("%Y-%m"))
        self.assertEqual(body["courseSales"][-1], 1)
        self.assertEqual(sum(body["courseSales"]), 1)

    def test_payment_chart_covers_thirty_days_ending_today(self):
        self.pay(500)
        self.pay(250)

        body = self.client.get(PAYMENTS_URL, **self.auth).json()

        self.assertEqual(len(body["allDays"]), 30)
        self.assertEqual(body["allDays"][-1], timezone.localdate().isoformat())
        self.assertEqual(body["income"][-1], 750)

    def test_teachers_cannot_see_the_money(self):
        teacher = bearer(make_user(role=User.Role.TEACHER))
        for url in (SALES_URL, PAYMENTS_URL):
            self.assertEqual(self.client.get(url, **teacher).status_code, 403)

        body = self.client.get(SUMMARY_URL, **teacher).json()
        self.assertIsNone(body["income"])
        self.assertIsNone(body["orders"])

    def test_a_teacher_counts_only_their_own_courses_and_students(self):
        teacher = make_user(role=User.Role.TEACHER)
        mine, theirs = (
            Course.objects.create(title="Mine", slug="mine-dash"),
            Course.objects.create(title="Theirs", slug="theirs-dash"),
        )
        CourseTeacher.objects.create(course=mine, user=teacher)
        other = make_user()
        Enrollment.objects.create(course=mine, user=self.student)
        Enrollment.objects.create(course=theirs, user=other)
        old = Enrollment.objects.create(course=mine, user=make_user())
        Enrollment.objects.filter(pk=old.pk).update(created_at=self.now - timezone.timedelta(days=400))

        body = self.client.get(SUMMARY_URL, **bearer(teacher)).json()

        self.assertEqual(body["totalCounts"], {"courses": 1, "students": 2})
        self.assertEqual(body["studentsRegistered"]["thisMonth"], 1)

    def test_students_cannot_see_the_dashboard(self):
        self.assertEqual(self.client.get(SUMMARY_URL, **bearer(self.student)).status_code, 403)
