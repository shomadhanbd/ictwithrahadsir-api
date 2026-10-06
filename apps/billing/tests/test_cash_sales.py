from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Payment, Product
from apps.billing.tests.base import BillingTestBase
from apps.core.testing import bearer, make_user
from apps.courses.models import CourseTeacher, Enrollment
from apps.identity.models import User

CASH_URL = reverse('api:billing:admin_cash_sale')


class CashSaleTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        self.admin = make_user(role=User.Role.ADMIN)

    def record(self, auth=None, **body):
        payload = {
            'user_id': self.student.pk,
            'course_id': self.live.pk,
            'product_id': self.product.pk,
            'amount': 450,
            **body,
        }
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(CASH_URL, payload, format='json', **(auth or bearer(self.admin)))

    def test_a_cash_sale_is_a_paid_payment_and_enrols(self):
        until = timezone.now() + timezone.timedelta(days=30)
        response = self.record(valid_till=until.isoformat(), note='Paid at the desk')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['method'], 'cash')

        payment = Payment.objects.get()
        self.assertEqual(
            (payment.status, payment.method, payment.amount, payment.recorded_by),
            (Payment.Status.VALID, Payment.Method.CASH, 450, self.admin),
        )
        for course in (self.live, self.recorded):
            enrolment = self.enrolment(course)
            self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)
            self.assertAlmostEqual(enrolment.valid_till, until, delta=timezone.timedelta(seconds=1))

    def test_no_end_date_lasts_as_long_as_the_package(self):
        """A year's package sold in cash is a year, not lifetime."""
        self.assertEqual(self.record().status_code, 201)
        year = timezone.now() + timezone.timedelta(days=365)
        self.assertAlmostEqual(self.enrolment(self.live).valid_till, year, delta=timezone.timedelta(minutes=1))

    def test_a_package_that_has_ended_needs_an_explicit_end_date(self):
        ended = timezone.localdate() - timezone.timedelta(days=2)
        Product.objects.filter(pk=self.product.pk).update(access_days=None, access_ends_on=ended)

        response = self.record()
        self.assertEqual(response.status_code, 422)
        self.assertIn('valid_till', response.json()['errors'])
        self.assertFalse(Payment.objects.exists())

        later = (timezone.now() + timezone.timedelta(days=30)).isoformat()
        self.assertEqual(self.record(valid_till=later).status_code, 201)

    def test_a_cash_sale_is_refused_while_the_package_is_still_running(self):
        """The same rule as online: one running purchase per package."""
        self.assertEqual(self.record().status_code, 201)
        response = self.record()
        self.assertEqual(response.status_code, 422)
        self.assertIn('renew it after that', str(response.json()['errors']))
        self.assertEqual(Payment.objects.count(), 1)

    def test_no_end_date_on_a_lifetime_package_is_lifetime(self):
        Product.objects.filter(pk=self.product.pk).update(access_days=None)
        self.assertEqual(self.record().status_code, 201)
        self.assertIsNone(self.enrolment(self.live).valid_till)

    def test_the_package_must_include_the_course(self):
        response = self.record(course_id=self.course.pk)
        self.assertEqual(response.status_code, 422)
        self.assertIn('product_id', response.json()['errors'])
        self.assertFalse(Payment.objects.exists())

    def test_amount_must_be_positive(self):
        self.assertEqual(self.record(amount=0).status_code, 422)

    def test_a_teacher_records_only_for_their_own_course(self):
        teacher = make_user(role=User.Role.TEACHER)
        self.assertEqual(self.record(auth=bearer(teacher)).status_code, 403)
        CourseTeacher.objects.create(course=self.live, user=teacher)
        self.assertEqual(self.record(auth=bearer(teacher)).status_code, 201)

    def test_a_free_enrolment_records_no_payment(self):
        body = {'slugOrId': self.course.pk, 'user_id': self.student.pk}
        response = self.client.post(reverse('api:courses:admin_enrollment'), body, format='json', **bearer(self.admin))
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Payment.objects.exists())
