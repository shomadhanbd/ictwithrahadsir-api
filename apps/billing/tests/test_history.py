from django.db.models import ProtectedError
from django.urls import reverse

from apps.billing.models import Payment
from apps.billing.tests.base import (
    MY_PAYMENTS_URL,
    BillingTestBase,
)
from apps.core.testing import make_user


class HistoryTests(BillingTestBase):
    def test_a_student_sees_only_their_own_payments(self):
        mine = self.started()
        self.capture(mine)
        other = make_user()
        Payment.objects.create(user=other, product=self.product, amount=500)

        payments = self.client.get(MY_PAYMENTS_URL, **self.auth).json()['data']
        self.assertEqual([p['transaction_id'] for p in payments], [mine.transaction_id])
        self.assertEqual((payments[0]['title'], payments[0]['status']), ('HSC ICT Package', 'VALID'))

        url = reverse('api:billing:my_payment_detail', args=[mine.transaction_id])
        detail = self.client.get(url, **self.auth).json()
        self.assertEqual(detail['status'], 'VALID')
        self.assertEqual(
            sorted(c['slug'] for c in detail['courses']),
            sorted(self.product.courses.values_list('slug', flat=True)),
        )


class RecordTests(BillingTestBase):
    """A payment is a financial record and outlives what it points at."""

    def test_a_product_somebody_paid_for_cannot_be_deleted(self):
        self.started()
        with self.assertRaises(ProtectedError):
            self.product.delete()

    def test_deleting_the_user_keeps_the_payment(self):
        payment = self.started()
        self.student.delete()
        payment.refresh_from_db()
        self.assertIsNone(payment.user)
