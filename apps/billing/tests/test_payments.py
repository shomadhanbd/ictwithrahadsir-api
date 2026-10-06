from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

import requests
from sslcommerz_lib import SSLCOMMERZ

from apps.billing.models import Payment, Product
from apps.billing.selectors import CHECKOUT_OPENING_SECONDS, CHECKOUT_REUSE_MINUTES
from apps.billing.services.sslcommerz import GATEWAY_TIMEOUT_SECONDS
from apps.billing.tests.base import (
    CANCEL,
    CAPTURE_URL,
    FAIL,
    GATEWAY_PAGE,
    INITIATE_URL,
    IPN_URL,
    STORE_PASSWORD,
    SUCCESS,
    BillingTestBase,
    signed,
    validator,
)
from apps.core.tests.test_admin import render_admin_templates
from apps.courses.models import Enrollment
from apps.identity.models import User


class InitiatePaymentTests(BillingTestBase):
    def test_a_product_opens_a_gateway_session(self):
        response, create_session = self.initiate(product_id='hsc-ict')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['gateway_page_url'], GATEWAY_PAGE)
        payment = Payment.objects.get(transaction_id=response.json()['transaction_id'])
        sent = create_session.call_args.args[0]
        self.assertEqual(sent['total_amount'], 500)
        self.assertEqual(sent['tran_id'], payment.transaction_id)
        self.assertEqual(sent['value_a'], str(self.student.pk))
        self.assertEqual(sent['success_url'], 'https://api.test/api/public/payments/capture/')
        self.assertEqual(sent['ipn_url'], 'https://api.test/api/public/payments/ipn/')
        self.assertEqual(sent['product_profile'], 'non-physical-goods')
        self.assertEqual(
            (payment.status, payment.product, payment.amount), (Payment.Status.INITIATED, self.product, 500)
        )
        self.assertAlmostEqual(
            payment.access_until, timezone.now() + timezone.timedelta(days=365), delta=timezone.timedelta(minutes=1)
        )

    def test_only_a_product_on_sale_can_be_bought(self):
        Product.objects.create(title='Retired', product_id='retired', price=100, base_price=100, is_active=False)
        for body in ({}, {'product_id': 'nope'}, {'product_id': 'retired'}):
            with self.subTest(body=body):
                self.assertEqual(self.initiate(**body)[0].status_code, 422)
        self.assertFalse(Payment.objects.exists())

    def test_a_product_cannot_be_bought_while_its_access_runs(self):
        failed = self.started()
        self.client.post(CAPTURE_URL, signed(tran_id=failed.transaction_id, status='FAILED'))
        self.capture(self.started())

        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('renew it after that', str(response.json()['errors']['product_id']))
        create_session.assert_not_called()

    def test_a_package_ending_today_is_not_sold(self):
        Product.objects.filter(pk=self.product.pk).update(access_days=None, access_ends_on=timezone.localdate())
        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        create_session.assert_not_called()

    def test_a_product_can_be_renewed_once_its_access_has_ended(self):
        self.capture(self.started())
        Payment.objects.update(access_until=timezone.now() - timezone.timedelta(days=1))

        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 201)
        create_session.assert_called_once()
        renewal = Payment.objects.latest('id')
        self.assertGreater(renewal.access_until, timezone.now() + timezone.timedelta(days=364))

    def test_a_lifetime_product_is_bought_once(self):
        Product.objects.filter(pk=self.product.pk).update(access_days=None)
        self.capture(self.started())

        response, _ = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('already bought', str(response.json()['errors']['product_id']))

    def test_a_refused_session_leaves_no_payment(self):
        refused = {'status': 'FAILED', 'failedreason': 'Store Credential Error'}
        with patch.object(SSLCOMMERZ, 'createSession', return_value=refused):
            response = self.client.post(INITIATE_URL, {'product_id': 'hsc-ict'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Payment.objects.exists())

    def test_an_unreachable_gateway_leaves_no_payment(self):
        with patch.object(SSLCOMMERZ, 'createSession', return_value=None):
            response = self.client.post(INITIATE_URL, {'product_id': 'hsc-ict'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Payment.objects.exists())

    def test_a_free_product_skips_the_gateway(self):
        Product.objects.filter(pk=self.product.pk).update(price=0)
        with self.captureOnCommitCallbacks(execute=True):
            response, create_session = self.initiate(product_id='hsc-ict')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()['gateway_page_url'])
        create_session.assert_not_called()
        self.assertEqual(Payment.objects.get().status, Payment.Status.VALID)
        self.assertTrue(Enrollment.objects.filter(user=self.student, course=self.live).exists())

    def test_a_price_under_the_gateway_minimum_is_refused(self):
        Product.objects.filter(pk=self.product.pk).update(price=5)
        self.assertEqual(self.initiate(product_id='hsc-ict')[0].status_code, 422)

    @override_settings(PAYMENT_INITIATE_RATE_LIMIT_PER_USER_PER_HOUR=2)
    def test_initiating_is_throttled_per_user(self):
        for _ in range(2):
            self.age(self.started(), minutes=CHECKOUT_REUSE_MINUTES + 1)
        self.assertEqual(self.initiate(product_id='hsc-ict')[0].status_code, 429)

    def age(self, payment, *, minutes):
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=minutes))

    def test_starting_the_same_checkout_again_reopens_it(self):
        """A double click or a second tab gets the same gateway page, so it cannot be paid twice."""
        first = self.started()
        response, create_session = self.initiate(product_id='hsc-ict')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'transaction_id': first.transaction_id, 'gateway_page_url': GATEWAY_PAGE})
        create_session.assert_not_called()
        self.assertEqual(Payment.objects.count(), 1)

    def opening(self, **age):
        """A checkout created moments ago, still waiting on its gateway page."""
        payment = Payment.objects.create(user=self.student, product=self.product, amount=500)
        if age:
            Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timezone.timedelta(**age))
        return payment

    def test_a_checkout_already_opening_is_not_opened_twice(self):
        """Two clicks at once: the second must not open a second gateway session."""
        self.opening()
        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('already opening', str(response.json()['errors']))
        create_session.assert_not_called()
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_checkout_that_never_got_its_page_stops_blocking(self):
        self.opening(seconds=CHECKOUT_OPENING_SECONDS + 1)
        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 201)
        create_session.assert_called_once()

    def test_a_free_package_is_claimed_once(self):
        Product.objects.filter(pk=self.product.pk).update(price=0)
        with self.captureOnCommitCallbacks(execute=True):
            first, _ = self.initiate(product_id='hsc-ict')
        second, _ = self.initiate(product_id='hsc-ict')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 422)
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_checkout_opened_before_the_package_changed_is_not_reopened(self):
        self.started()
        self.product.access_days = 30
        self.product.save()
        response, create_session = self.initiate(product_id='hsc-ict')
        create_session.assert_called_once()
        self.assertEqual(Payment.objects.count(), 2)

    def test_a_stale_checkout_is_not_reopened(self):
        self.age(self.started(), minutes=CHECKOUT_REUSE_MINUTES + 1)
        response, create_session = self.initiate(product_id='hsc-ict')
        create_session.assert_called_once()
        self.assertEqual(Payment.objects.count(), 2)

    def test_the_gateway_call_has_a_timeout(self):
        page = {'status': 'SUCCESS', 'GatewayPageURL': GATEWAY_PAGE}
        with patch('apps.billing.services.sslcommerz.http_requests.post') as post:
            post.return_value.json.return_value = page
            response = self.client.post(INITIATE_URL, {'product_id': 'hsc-ict'}, format='json', **self.auth)
            self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(post.call_args.kwargs['timeout'], GATEWAY_TIMEOUT_SECONDS)

    def test_a_gateway_timeout_leaves_no_payment(self):
        with patch('apps.billing.services.sslcommerz.http_requests.post', side_effect=requests.Timeout):
            response = self.client.post(INITIATE_URL, {'product_id': 'hsc-ict'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Payment.objects.exists())


class CaptureTests(BillingTestBase):
    def redirect(self, response):
        location = urlparse(response['Location'])
        return f'{location.scheme}://{location.netloc}{location.path}', parse_qs(location.query).get('tran_id')

    def test_a_valid_payment_enrols_on_every_course_it_unlocks(self):
        payment = self.started()
        response = self.capture(payment)

        self.assertEqual(self.redirect(response), (SUCCESS, [payment.transaction_id]))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VALID)
        year = timezone.now() + timezone.timedelta(days=365)
        for course in (self.live, self.recorded):
            with self.subTest(course=course.title):
                enrolment = self.enrolment(course)
                self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)
                self.assertAlmostEqual(enrolment.valid_till, year, delta=timezone.timedelta(minutes=1))

    def test_the_access_length_is_fixed_when_the_payment_starts(self):
        payment = self.started()
        self.product.access_days = 7
        self.product.save()

        self.capture(payment)
        self.assertGreater(self.enrolment(self.live).valid_till, timezone.now() + timezone.timedelta(days=300))

    def test_a_payment_the_validator_disowns_fails(self):
        cases = {
            'invalid': {'status': 'INVALID_TRANSACTION'},
            'wrong amount': {'amount': '1.00'},
            'wrong tran_id': {'tran_id': 'someone-else'},
            'another user': {'value_a': '999999'},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                payment = self.started()
                response = self.capture(payment, **overrides)
                payment.refresh_from_db()
                self.assertEqual(payment.status, Payment.Status.FAILED)
                self.assertEqual(self.redirect(response)[0], FAIL)
                self.assertFalse(Enrollment.objects.exists())

    def test_an_unreachable_validator_leaves_it_for_the_ipn(self):
        payment = self.started()
        with patch('apps.billing.services.sslcommerz.http_requests.get', side_effect=requests.ConnectionError):
            response = self.client.post(
                CAPTURE_URL, signed(tran_id=payment.transaction_id, val_id='VAL-1', status='VALID')
            )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.INITIATED)
        self.assertEqual(self.redirect(response)[0], SUCCESS)

    def capture_checked_before(self, payment):
        with validator(payment, status='VALIDATED'), self.captureOnCommitCallbacks(execute=True):
            return self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, val_id='VAL-1', status='VALID'))

    def test_a_val_id_the_validator_already_checked_still_settles(self):
        """SSLCommerz answers VALIDATED, not VALID, the second time a val_id is checked."""
        payment = self.started()
        response = self.capture_checked_before(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VALID)
        self.assertEqual(self.redirect(response)[0], SUCCESS)
        self.assertTrue(Enrollment.objects.filter(course=self.live).exists())

    def test_a_timed_out_check_is_settled_by_the_next_report(self):
        """The first check reached SSLCommerz but timed out here, so every later one says VALIDATED."""
        payment = self.started()
        with patch('apps.billing.services.sslcommerz.http_requests.get', side_effect=requests.Timeout):
            self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, val_id='VAL-1', status='VALID'))
        self.capture_checked_before(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VALID)

    def test_a_failed_validator_call_never_logs_the_store_password(self):
        payment = self.started()
        error = requests.ConnectionError(f'Max retries exceeded with url: /validator?store_passwd={STORE_PASSWORD}')
        with (
            patch('apps.billing.services.sslcommerz.http_requests.get', side_effect=error),
            self.assertLogs('payments', level='WARNING') as logs,
        ):
            self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, val_id='VAL-1', status='VALID'))
        self.assertTrue(logs.output)
        self.assertNotIn(STORE_PASSWORD, '\n'.join(logs.output))

    def test_fail_and_cancel(self):
        for status, page in (('FAILED', FAIL), ('CANCELLED', CANCEL)):
            with self.subTest(status):
                payment = self.started()
                response = self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, status=status))
                payment.refresh_from_db()
                self.assertEqual(payment.status, status)
                self.assertEqual(self.redirect(response)[0], page)

    def test_a_late_failure_cannot_undo_a_valid_payment(self):
        payment = self.started()
        self.capture(payment)
        self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, status='FAILED'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VALID)

    def test_a_late_valid_still_settles_a_failed_payment(self):
        payment = self.started()
        self.client.post(CAPTURE_URL, signed(tran_id=payment.transaction_id, status='FAILED'))
        self.capture(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VALID)

    def test_an_unsigned_callback_changes_nothing(self):
        payment = self.started()
        response = self.client.post(CAPTURE_URL, {'tran_id': payment.transaction_id, 'status': 'CANCELLED'})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.INITIATED)
        self.assertEqual(response['Location'], FAIL)


class IpnTests(BillingTestBase):
    def ipn(self, payment, **body):
        with validator(payment), self.captureOnCommitCallbacks(execute=True):
            return self.client.post(IPN_URL, signed(tran_id=payment.transaction_id, **body))

    def test_the_ipn_settles_a_payment(self):
        payment = self.started()
        response = self.ipn(payment, val_id='VAL-1', status='VALID')
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VALID)
        self.assertTrue(Enrollment.objects.filter(course=self.live).exists())

    def test_a_second_report_grants_nothing_twice(self):
        """The capture redirect and the IPN both arrive."""
        payment = self.started()
        self.capture(payment)
        with patch('apps.billing.signals.grant_purchased_access') as grant:
            self.ipn(payment, val_id='VAL-1', status='VALID')
            payment.refresh_from_db()
            payment.save()
        grant.assert_not_called()

    def test_a_callback_naming_a_field_it_lacks_is_refused_not_a_500(self):
        payment = self.started()
        body = {
            'tran_id': payment.transaction_id,
            'status': 'VALID',
            'verify_key': 'tran_id,amount',
            'verify_sign': 'x',
        }
        self.assertEqual(self.client.post(IPN_URL, body).status_code, 200)
        self.assertEqual(self.client.post(CAPTURE_URL, body).status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.INITIATED)

    def test_the_ipn_always_answers_200(self):
        payment = self.started()
        for body in ({'tran_id': 'unknown', 'status': 'VALID'}, {'tran_id': payment.transaction_id}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(IPN_URL, body).status_code, 200)
                self.assertEqual(self.client.post(IPN_URL, signed(**body)).status_code, 200)


class DuplicatePurchaseTests(BillingTestBase):
    def test_a_second_paid_checkout_is_flagged_for_refund(self):
        first = self.started()
        Payment.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timezone.timedelta(minutes=CHECKOUT_REUSE_MINUTES + 1)
        )
        second = self.started()
        self.capture(first)
        self.capture(second)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), (Payment.Status.VALID, Payment.Status.VALID))
        self.assertEqual(first.note, '')
        self.assertIn(f'Duplicate of {first.transaction_id}', second.note)

    def test_a_duplicate_neither_extends_access_nor_texts_the_buyer(self):
        first = self.started()
        self.capture(first)
        Payment.objects.filter(pk=first.pk).update(note='Paid at the counter.')
        before = self.enrolment(self.live).valid_till
        second = Payment.objects.create(
            user=self.student,
            product=self.product,
            amount=500,
            access_until=timezone.now() + timezone.timedelta(days=400),
            note='Second tab.',
        )

        self.capture(second)

        second.refresh_from_db()
        self.assertEqual(second.note, f'Second tab. Duplicate of {first.transaction_id}: refund.')
        self.assertEqual(self.enrolment(self.live).valid_till, before)

    def test_a_refunded_duplicate_does_not_block_renewal(self):
        """It gave no access, so once the real access ends the package can be bought again."""
        first = self.started()
        self.capture(first)
        duplicate = Payment.objects.create(user=self.student, product=self.product, amount=500)
        self.capture(duplicate)
        duplicate.refresh_from_db()
        self.assertTrue(duplicate.refund_due)

        Payment.objects.filter(pk=first.pk).update(access_until=timezone.now() - timezone.timedelta(days=1))
        response, _ = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_renewal_after_access_ended_is_not_a_duplicate(self):
        first = self.started()
        self.capture(first)
        Payment.objects.filter(pk=first.pk).update(access_until=timezone.now() - timezone.timedelta(days=1))
        renewal = self.started()
        self.capture(renewal)
        renewal.refresh_from_db()
        self.assertEqual(renewal.note, '')


@render_admin_templates
class PaymentAdminTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(phone='01700000009', password='Str0ngPass!23', name='Admin')
        self.client.force_login(self.staff)
        self.payment = self.started()

    def test_marking_a_stuck_payment_paid_grants_access(self):
        payment_admin = admin.site._registry[Payment]
        request = RequestFactory().post('/')
        request.user = self.staff
        with patch.object(payment_admin, 'message_user'), self.captureOnCommitCallbacks(execute=True):
            payment_admin.mark_paid(request, Payment.objects.filter(pk=self.payment.pk))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.VALID)
        self.assertIn('Marked paid by', self.payment.note)
        self.assertTrue(Enrollment.objects.filter(user=self.student, course=self.live).exists())

    def mark_paid(self, *payments):
        payment_admin = admin.site._registry[Payment]
        request = RequestFactory().post('/')
        request.user = self.staff
        with patch.object(payment_admin, 'message_user') as message, self.captureOnCommitCallbacks(execute=True):
            payment_admin.mark_paid(request, Payment.objects.filter(pk__in=[p.pk for p in payments]))
        return message.call_args.args[1]

    def test_marking_paid_a_package_the_buyer_already_has_is_a_duplicate(self):
        self.capture(self.payment)
        before = self.enrolment(self.live).valid_till
        failed = Payment.objects.create(
            user=self.student,
            product=self.product,
            amount=500,
            status=Payment.Status.FAILED,
            access_until=timezone.now() + timezone.timedelta(days=400),
        )

        message = self.mark_paid(failed)

        failed.refresh_from_db()
        self.assertIn(f'Duplicate of {self.payment.transaction_id}: refund.', failed.note)
        self.assertEqual(self.enrolment(self.live).valid_till, before)
        self.assertIn('1 duplicate(s) noted for refund', message)

    def test_a_duplicate_marked_paid_keeps_its_own_dates(self):
        self.capture(self.payment)
        stuck = Payment.objects.create(user=self.student, product=self.product, amount=500, access_until=None)
        self.mark_paid(stuck)
        stuck.refresh_from_db()
        self.assertTrue(stuck.refund_due)
        self.assertIsNone(stuck.access_until)

    def test_access_runs_from_when_it_is_marked_paid(self):
        """The checkout was started a week ago; the year starts now, not then."""
        Payment.objects.filter(pk=self.payment.pk).update(access_until=timezone.now() + timezone.timedelta(days=358))
        self.mark_paid(self.payment)
        year = timezone.now() + timezone.timedelta(days=365)
        self.payment.refresh_from_db()
        self.assertAlmostEqual(self.payment.access_until, year, delta=timezone.timedelta(minutes=1))

    def test_paid_payments_and_ones_without_a_buyer_are_skipped(self):
        self.capture(self.payment)
        orphan = Payment.objects.create(user=None, product=self.product, amount=500)
        message = self.mark_paid(self.payment, orphan)
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, Payment.Status.INITIATED)
        self.assertIn('0 marked paid', message)
        self.assertIn('2 skipped', message)

    def test_status_and_amount_cannot_be_edited_by_hand(self):
        page = self.client.get(reverse('admin:billing_payment_change', args=[self.payment.pk]))
        form = page.context['adminform'].form
        for field in ('status', 'amount', 'access_until', 'user', 'product'):
            with self.subTest(field=field):
                self.assertNotIn(field, form.fields)
