"""Renewing a fixed-days package in its last days: the new days are added to the end of the running ones."""

from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Payment
from apps.billing.tests.base import BillingTestBase
from apps.courses.models import Enrollment

DAY = timezone.timedelta(days=1)


class RenewalTests(BillingTestBase):
    def bought(self, *, ends_in):
        """A paid year's package whose access now ends in `ends_in`."""
        payment = self.started()
        self.capture(payment)
        ends = timezone.now() + ends_in
        Payment.objects.filter(pk=payment.pk).update(access_until=ends)
        Enrollment.objects.filter(user=self.student).update(valid_till=ends)
        return ends

    def test_a_package_ending_soon_is_renewed_from_its_end(self):
        ends = self.bought(ends_in=2 * DAY)

        renewal = self.started()
        self.assertAlmostEqual(renewal.access_until, ends + 365 * DAY, delta=timezone.timedelta(seconds=1))
        self.capture(renewal)

        renewal.refresh_from_db()
        self.assertFalse(renewal.refund_due)
        for course in (self.live, self.recorded):
            self.assertAlmostEqual(
                self.enrolment(course).valid_till, ends + 365 * DAY, delta=timezone.timedelta(seconds=1)
            )

    def test_renewal_opens_only_in_the_last_days(self):
        self.bought(ends_in=10 * DAY)
        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('renew it from', str(response.json()['errors']['product_id']))
        create_session.assert_not_called()

    def test_a_fixed_date_package_is_not_renewed_early(self):
        self.bought(ends_in=2 * DAY)
        self.product.access_days = None
        self.product.access_ends_on = timezone.localdate() + 60 * DAY
        self.product.save()
        response, _ = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('renew it after that', str(response.json()['errors']['product_id']))

    def test_a_second_renewal_paid_alongside_is_a_duplicate(self):
        self.bought(ends_in=2 * DAY)
        renewal = self.started()
        twin = Payment.objects.create(
            user=self.student, product=self.product, amount=renewal.amount, access_until=renewal.access_until
        )
        self.capture(renewal)
        self.capture(twin)
        twin.refresh_from_db()
        self.assertTrue(twin.refund_due)

    def test_the_course_page_says_when_renewal_is_open(self):
        url = reverse('api:courses:course_detail', args=[self.live.slug])
        self.bought(ends_in=10 * DAY)
        self.assertFalse(self.client.get(url, **self.auth).json()['enrollment']['renewable'])
        Enrollment.objects.filter(user=self.student).update(valid_till=timezone.now() + 2 * DAY)
        self.assertTrue(self.client.get(url, **self.auth).json()['enrollment']['renewable'])
