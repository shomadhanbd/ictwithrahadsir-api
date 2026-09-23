"""Products, coupons, orders and SSLCommerz payments.

SSLCommerz is never contacted: `requests` inside `apps.billing.sslcommerz` is
patched, and each test says what the gateway answers.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

import requests
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.billing import selectors, services
from apps.billing.models import Order, Payment, Product, ProductCoupon
from apps.courses.models import Coupon, Course, CoursePrice, Enrollment
from apps.identity.models import User

ORDER_URL = reverse('api:billing:orders')
MY_ORDERS_URL = reverse('api:billing:orders')
FREE_PURCHASE_URL = reverse('api:billing:free_enrollment')
ADMIN_PAYMENT_URL = reverse('api:billing:admin_payment_list')


class ShopTestBase(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(phone='01810400001', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}


class OrderTests(ShopTestBase):
    def setUp(self):
        super().setUp()
        self.course = Course.objects.create(title='ICT', slug='ict', active=True)
        self.price = CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=self.course.id,
            title='Full',
            amount=Decimal('1500'),
        )

    def test_an_order_is_created_at_the_list_price(self):
        response = self.client.post(
            ORDER_URL,
            {'course_id': self.course.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Order.objects.get().amount, Decimal('1500'))

    def test_a_live_discount_is_applied(self):
        self.price.discount = Decimal('300')
        self.price.discount_till = timezone.now() + timezone.timedelta(days=1)
        self.price.save()

        self.client.post(
            ORDER_URL,
            {'course_id': self.course.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(Order.objects.get().amount, Decimal('1200'))

    def test_an_expired_discount_is_ignored(self):
        self.price.discount = Decimal('300')
        self.price.discount_till = timezone.now() - timezone.timedelta(days=1)
        self.price.save()

        self.client.post(
            ORDER_URL,
            {'course_id': self.course.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(Order.objects.get().amount, Decimal('1500'))

    def test_a_price_from_another_course_is_rejected(self):
        other = Course.objects.create(title='Other', slug='other', active=True)
        response = self.client.post(
            ORDER_URL,
            {'course_id': other.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_orders_lists_only_the_callers_own(self):
        Order.objects.create(user=self.student, course=self.course, amount=Decimal('1'), total=Decimal('1'))
        other = User.objects.create_user(phone='01810400002', name='Other', password='Str0ngPass!23')
        Order.objects.create(user=other, course=self.course, amount=Decimal('2'), total=Decimal('2'))
        body = self.client.get(MY_ORDERS_URL, **self.auth).json()
        self.assertEqual(len(body['data']), 1)


class AdminPaymentTests(ShopTestBase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_user(
            phone='01710400001',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.admin_auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.course = Course.objects.create(title='ICT', slug='ict', active=True)
        self.order = Order.objects.create(
            user=self.student,
            course=self.course,
            amount=Decimal('1500'),
            total=Decimal('1500'),
        )
        # A payment from the retired manual flow: an admin still settles those.
        self.payment = Payment.objects.create(
            order=self.order, amount=Decimal('1500'), transaction_id='TRX', vendor=Payment.Vendor.BKASH
        )

    def url(self):
        return reverse('api:billing:admin_payment_update', args=[self.payment.pk])

    def test_students_cannot_list_payments(self):
        self.assertEqual(self.client.get(ADMIN_PAYMENT_URL, **self.auth).status_code, 403)

    def test_confirming_a_payment_enrols_the_student(self):
        response = self.client.patch(self.url(), {'status': 'successful'}, format='json', **self.admin_auth)
        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        enrolment = Enrollment.objects.get(course=self.course, user=self.student)
        self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)

    def test_failing_a_payment_fails_the_order_without_enrolling(self):
        self.client.patch(self.url(), {'status': 'failed'}, format='json', **self.admin_auth)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.FAILED)
        self.assertFalse(Enrollment.objects.exists())

    def test_confirming_a_short_payment_is_refused(self):
        # New payments always carry the order's amount, but rows written
        # before that fix may not -- confirming one grants course access.
        Payment.objects.filter(pk=self.payment.pk).update(amount=Decimal('1'))

        response = self.client.patch(self.url(), {'status': 'successful'}, format='json', **self.admin_auth)
        self.assertEqual(response.status_code, 422)
        self.assertIn('amount', response.json()['errors'])

        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, Order.Status.PAID)
        self.assertFalse(Enrollment.objects.exists())

    def test_a_mismatch_can_be_confirmed_deliberately(self):
        Payment.objects.filter(pk=self.payment.pk).update(amount=Decimal('1'))

        response = self.client.patch(
            self.url(),
            {'status': 'successful', 'confirm_amount_mismatch': True},
            format='json',
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_the_amount_check_does_not_block_failing_a_payment(self):
        Payment.objects.filter(pk=self.payment.pk).update(amount=Decimal('1'))
        response = self.client.patch(self.url(), {'status': 'failed'}, format='json', **self.admin_auth)
        self.assertEqual(response.status_code, 200)

    def test_an_invalid_status_is_rejected(self):
        response = self.client.patch(self.url(), {'status': 'maybe'}, format='json', **self.admin_auth)
        self.assertEqual(response.status_code, 422)


class FreeCoursePurchaseTests(ShopTestBase):
    def setUp(self):
        super().setUp()
        self.course = Course.objects.create(title='Free ICT', slug='free-ict', active=True)

    def test_a_course_with_no_prices_can_be_claimed(self):
        response = self.client.post(FREE_PURCHASE_URL, {'course_id': self.course.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Enrollment.objects.filter(course=self.course).exists())

    def test_a_zero_priced_course_can_be_claimed(self):
        CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=self.course.id,
            title='Free',
            amount=Decimal('0'),
        )
        response = self.client.post(FREE_PURCHASE_URL, {'course_id': self.course.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_a_paid_course_cannot_be_claimed_for_free(self):
        CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=self.course.id,
            title='Full',
            amount=Decimal('1500'),
        )
        response = self.client.post(FREE_PURCHASE_URL, {'course_id': self.course.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Enrollment.objects.exists())


class PaymentConfirmationAtomicityTests(ShopTestBase):
    """Confirming a payment writes three rows across two apps.

    It must be all-or-nothing: a half-applied confirmation either takes a
    student's money without enrolling them, or enrols them against an order
    that still reads as unpaid.
    """

    def setUp(self):
        super().setUp()
        admin = User.objects.create_user(
            phone='01710400009',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.admin_auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.course = Course.objects.create(title='Atomic', slug='atomic', active=True)
        price = CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=self.course.id, title='Full', amount=1500
        )
        self.order = Order.objects.create(
            user=self.student,
            course=self.course,
            price=price,
            amount=Decimal('1500'),
            total=Decimal('1500'),
        )
        self.payment = Payment.objects.create(
            order=self.order, amount=Decimal('1500'), transaction_id='TRX-ATOMIC', vendor=Payment.Vendor.BKASH
        )

    def test_a_failure_granting_access_rolls_back_the_payment_and_order(self):
        url = reverse('api:billing:admin_payment_update', args=[self.payment.pk])

        failing_grant = patch(
            'apps.billing.services.grant_purchased_access',
            side_effect=RuntimeError('enrolment backend down'),
        )
        with failing_grant, self.assertRaises(RuntimeError):
            self.client.patch(url, {'status': 'successful'}, format='json', **self.admin_auth)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())


# ---------------------------------------------------------------------------
# Products, coupons and SSLCommerz
# ---------------------------------------------------------------------------

GATEWAY = override_settings(
    SSLCOMMERZ_STORE_ID='store',
    SSLCOMMERZ_STORE_PASSWORD='secret',
    SSLCOMMERZ_SANDBOX=True,
    API_BASE_URL='https://api.test',
    PAYMENT_RESULT_URL='https://site.test/payment/result',
)
GATEWAY_PAGE = 'https://sandbox.sslcommerz.com/EasyCheckOut/abc'


def fake_response(body):
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


def session_ok():
    return patch(
        'apps.billing.sslcommerz.requests.post',
        return_value=fake_response({'status': 'SUCCESS', 'GatewayPageURL': GATEWAY_PAGE}),
    )


def validation(payment, **overrides):
    """What SSLCommerz's validation API says about `payment`."""
    body = {
        'status': 'VALID',
        'tran_id': payment.transaction_id,
        'val_id': 'VAL-1',
        'amount': str(payment.amount),
        'currency_type': 'BDT',
        'currency_amount': str(payment.amount),
        'bank_tran_id': 'BANK-1',
        'card_type': 'BKASH-BKash',
        'risk_level': '0',
        **overrides,
    }
    return patch('apps.billing.sslcommerz.requests.get', return_value=fake_response(body))


@GATEWAY
class CheckoutTestBase(ShopTestBase):
    def setUp(self):
        super().setUp()
        self.course = Course.objects.create(title='ICT', slug='ict', active=True)
        # A bundle: one live course and one recorded, for a year.
        self.live = Course.objects.create(title='ICT Live Batch', slug='ict-live', active=True, is_online=True)
        self.recorded = Course.objects.create(title='ICT Recorded', slug='ict-rec', active=True, is_online=False)
        self.product = Product.objects.create(title='HSC ICT Package', amount=Decimal('500'), access_days=365)
        self.product.courses.set([self.live, self.recorded])
        self.price = CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=self.course.id,
            title='Full',
            amount=Decimal('1500'),
            validity_duration=30,
        )

    def order(self, **body):
        response = self.client.post(ORDER_URL, body, format='json', **self.auth)
        self.assertEqual(response.status_code, 201, response.content)
        return Order.objects.get(pk=response.json()['id'])

    def pay(self, order):
        with session_ok() as post:
            response = self.client.post(reverse('api:billing:order_pay', args=[order.pk]), **self.auth)
        return response, post

    def paid_order(self, **body):
        """An order placed, paid through the gateway, and settled VALID."""
        order = self.order(**body)
        self.pay(order)
        payment = order.payments.get()
        with validation(payment):
            services.complete_payment(tran_id=payment.transaction_id, val_id='VAL-1')
        return order


class ProductTests(CheckoutTestBase):
    PRODUCTS_URL = reverse('api:billing:products')
    MINE_URL = reverse('api:billing:my_products')

    def enrolment(self, course):
        return Enrollment.objects.filter(user=self.student, course=course).first()

    def test_the_public_list_shows_active_products_and_their_courses(self):
        Product.objects.create(title='Retired', amount=1, active=False)
        body = self.client.get(self.PRODUCTS_URL).json()
        self.assertEqual([p['title'] for p in body['data']], ['HSC ICT Package'])
        courses = {c['title']: c['is_online'] for c in body['data'][0]['courses']}
        self.assertEqual(courses, {'ICT Live Batch': True, 'ICT Recorded': False})

    def test_detail_by_slug_or_id(self):
        for key in (self.product.slug, self.product.pk):
            with self.subTest(key=key):
                url = reverse('api:billing:product_detail', args=[key])
                self.assertEqual(self.client.get(url).json()['title'], 'HSC ICT Package')

    def test_buying_a_product_enrols_on_every_course_it_unlocks(self):
        self.paid_order(product_id=self.product.pk)
        year = timezone.now() + timezone.timedelta(days=365)
        for course in (self.live, self.recorded):
            with self.subTest(course=course.title):
                enrolment = self.enrolment(course)
                self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)
                self.assertAlmostEqual(enrolment.valid_till, year, delta=timezone.timedelta(minutes=1))
        mine = self.client.get(self.MINE_URL, **self.auth).json()['data']
        self.assertEqual([p['title'] for p in mine], ['HSC ICT Package'])

    def test_an_unpaid_order_enrols_nobody(self):
        self.order(product_id=self.product.pk)
        self.assertFalse(Enrollment.objects.exists())
        self.assertEqual(self.client.get(self.MINE_URL, **self.auth).json()['data'], [])

    def test_a_product_with_neither_is_lifetime(self):
        self.product.access_days = None
        self.product.save()
        self.paid_order(product_id=self.product.pk)
        self.assertIsNone(self.enrolment(self.live).valid_till)

    def test_an_end_date_lasts_to_the_end_of_that_day(self):
        """A live batch that ends on a date."""
        ends = timezone.localdate() + timezone.timedelta(days=90)
        self.product.access_days = None
        self.product.access_ends_on = ends
        self.product.save()
        self.paid_order(product_id=self.product.pk)
        valid_till = timezone.localtime(self.enrolment(self.live).valid_till)
        self.assertEqual((valid_till.date(), valid_till.hour, valid_till.minute), (ends, 23, 59))

    def test_buying_again_renews(self):
        self.paid_order(product_id=self.product.pk)
        Enrollment.objects.update(valid_till=timezone.now() + timezone.timedelta(days=5))
        self.paid_order(product_id=self.product.pk)
        self.assertGreater(self.enrolment(self.live).valid_till, timezone.now() + timezone.timedelta(days=300))

    def test_a_purchase_never_shortens_access(self):
        """A lifetime student who buys a one-year bundle keeps lifetime access."""
        Enrollment.objects.create(user=self.student, course=self.live, payment_type=Enrollment.PaymentType.FREE)
        self.paid_order(product_id=self.product.pk)
        enrolment = self.enrolment(self.live)
        self.assertIsNone(enrolment.valid_till)
        self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)

    def test_an_order_is_a_course_or_a_product_not_both(self):
        response = self.client.post(
            ORDER_URL,
            {'product_id': self.product.pk, 'course_id': self.course.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)


class AdminProductTests(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_user(phone='01710400011', name='Admin', role=User.Role.ADMIN)
        self.admin_auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}

    def test_an_admin_creates_a_product_and_a_coupon(self):
        product = self.client.post(
            reverse('api:billing:admin-product-list'),
            {'title': 'Model Tests', 'amount': '300', 'course_ids': [self.course.pk], 'access_days': 180},
            format='json',
            **self.admin_auth,
        )
        self.assertEqual(product.status_code, 201, product.content)
        coupon = self.client.post(
            reverse('api:billing:admin-product-coupon-list'),
            {'product_id': product.json()['id'], 'code': 'eid10', 'discount': '10'},
            format='json',
            **self.admin_auth,
        )
        self.assertEqual(coupon.status_code, 201, coupon.content)
        self.assertEqual(coupon.json()['code'], 'EID10')

    def test_a_product_must_unlock_a_course(self):
        response = self.client.post(
            reverse('api:billing:admin-product-list'),
            {'title': 'Empty', 'amount': '300', 'course_ids': []},
            format='json',
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('course_ids', response.json()['errors'])

    def test_access_is_days_or_an_end_date_not_both(self):
        response = self.client.post(
            reverse('api:billing:admin-product-list'),
            {
                'title': 'X',
                'amount': '300',
                'course_ids': [self.course.pk],
                'access_days': 30,
                'access_ends_on': '2027-01-01',
            },
            format='json',
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('access_ends_on', response.json()['errors'])

    def test_a_percentage_over_100_is_refused(self):
        response = self.client.post(
            reverse('api:billing:admin-product-coupon-list'),
            {'product_id': self.product.pk, 'code': 'X', 'discount': '150'},
            format='json',
            **self.admin_auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_a_product_somebody_bought_cannot_be_deleted(self):
        self.order(product_id=self.product.pk)
        response = self.client.delete(
            reverse('api:billing:admin-product-detail', args=[self.product.pk]), **self.admin_auth
        )
        self.assertEqual(response.status_code, 409)

    def test_students_are_kept_out(self):
        self.assertEqual(self.client.get(reverse('api:billing:admin-product-list'), **self.auth).status_code, 403)


class CouponTests(CheckoutTestBase):
    QUOTE_URL = reverse('api:billing:order_quote')

    def quote(self, **body):
        return self.client.post(self.QUOTE_URL, body, format='json', **self.auth)

    def test_a_percentage_coupon(self):
        ProductCoupon.objects.create(product=self.product, code='TEN', discount=10)
        body = self.quote(product_id=self.product.pk, coupon_code='ten').json()
        self.assertEqual((body['coupon_discount'], body['total'], body['coupon_code']), ('50.00', '450.00', 'TEN'))

    def test_a_fixed_coupon_after_the_products_own_discount(self):
        self.product.discount = Decimal('100')
        self.product.save()
        ProductCoupon.objects.create(
            product=self.product, code='OFF50', discount=50, discount_type=Coupon.DiscountType.FIXED
        )
        self.assertEqual(self.quote(product_id=self.product.pk, coupon_code='OFF50').json()['total'], '350.00')

    def test_a_coupon_cannot_take_more_than_the_price(self):
        ProductCoupon.objects.create(
            product=self.product, code='ALL', discount=9999, discount_type=Coupon.DiscountType.FIXED
        )
        self.assertEqual(self.quote(product_id=self.product.pk, coupon_code='ALL').json()['total'], '0.00')

    def test_coupons_that_do_not_apply_are_refused(self):
        other = Product.objects.create(title='Other', amount=100)
        ProductCoupon.objects.create(product=other, code='OTHER', discount=10)
        ProductCoupon.objects.create(product=self.product, code='OFF', discount=10, active=False)
        ProductCoupon.objects.create(
            product=self.product, code='OLD', discount=10, valid_till=timezone.now() - timezone.timedelta(days=1)
        )
        for code in ('NOPE', 'OTHER', 'OFF', 'OLD'):
            with self.subTest(code=code):
                response = self.quote(product_id=self.product.pk, coupon_code=code)
                self.assertEqual(response.status_code, 422)
                self.assertIn('coupon_code', response.json()['errors'])

    def test_a_used_up_coupon_is_refused(self):
        ProductCoupon.objects.create(product=self.product, code='ONCE', discount=10, usage_limit=1)
        other = User.objects.create_user(phone='01810400099', name='Other')
        Order.objects.create(
            user=other, product=self.product, coupon_code='ONCE', amount=450, total=450, status=Order.Status.PAID
        )
        self.assertEqual(self.quote(product_id=self.product.pk, coupon_code='ONCE').status_code, 422)

    def test_a_course_coupon_applies(self):
        Coupon.objects.create(price=self.price, code='HSC20', discount=20)
        body = self.quote(course_id=self.course.pk, price_id=self.price.pk, coupon_code='hsc20').json()
        self.assertEqual(body['total'], '1200.00')

    def test_a_total_under_the_gateway_minimum_is_refused(self):
        ProductCoupon.objects.create(
            product=self.product, code='BIG', discount=495, discount_type=Coupon.DiscountType.FIXED
        )
        self.assertEqual(self.quote(product_id=self.product.pk, coupon_code='BIG').status_code, 422)

    def test_a_quote_places_nothing(self):
        self.quote(product_id=self.product.pk)
        self.assertFalse(Order.objects.exists())

    def test_the_order_keeps_the_coupon(self):
        ProductCoupon.objects.create(product=self.product, code='TEN', discount=10)
        order = self.order(product_id=self.product.pk, coupon_code='TEN')
        self.assertEqual((order.coupon_code, order.coupon_discount, order.total), ('TEN', 50, 450))


class StartPaymentTests(CheckoutTestBase):
    def test_the_gateway_is_asked_for_the_order_total(self):
        order = self.order(product_id=self.product.pk)
        response, post = self.pay(order)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['gateway_url'], GATEWAY_PAGE)
        sent = post.call_args.kwargs['data']
        payment = order.payments.get()
        self.assertEqual(sent['total_amount'], '500.00')
        self.assertEqual(sent['currency'], 'BDT')
        self.assertEqual(sent['tran_id'], payment.transaction_id)
        self.assertEqual(sent['product_profile'], 'non-physical-goods')
        self.assertEqual(sent['shipping_method'], 'NO')
        self.assertEqual(sent['ipn_url'], 'https://api.test/api/public/payments/sslcommerz/ipn/')
        self.assertEqual((payment.status, payment.vendor), (Payment.Status.PENDING, Payment.Vendor.SSLCOMMERZ))

    def test_a_gateway_failure_is_a_503_and_fails_the_payment(self):
        order = self.order(product_id=self.product.pk)
        refused = fake_response({'status': 'FAILED', 'failedreason': 'Store Credential Error'})
        with patch('apps.billing.sslcommerz.requests.post', return_value=refused):
            response = self.client.post(reverse('api:billing:order_pay', args=[order.pk]), **self.auth)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(order.payments.get().status, Payment.Status.FAILED)

    def test_an_unreachable_gateway_is_a_503(self):
        order = self.order(product_id=self.product.pk)
        with patch('apps.billing.sslcommerz.requests.post', side_effect=requests.ConnectionError):
            response = self.client.post(reverse('api:billing:order_pay', args=[order.pk]), **self.auth)
        self.assertEqual(response.status_code, 503)

    @override_settings(SSLCOMMERZ_STORE_ID='')
    def test_without_credentials_it_is_a_503(self):
        order = self.order(product_id=self.product.pk)
        response = self.client.post(reverse('api:billing:order_pay', args=[order.pk]), **self.auth)
        self.assertEqual(response.status_code, 503)

    def test_a_free_order_completes_without_the_gateway(self):
        ProductCoupon.objects.create(product=self.product, code='FREE', discount=100)
        order = self.order(product_id=self.product.pk, coupon_code='FREE')
        response, post = self.pay(order)

        self.assertIsNone(response.json()['gateway_url'])
        post.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_another_students_order_is_not_found(self):
        other = User.objects.create_user(phone='01810400098', name='Other')
        order = Order.objects.create(user=other, product=self.product, amount=500, total=500)
        response, _ = self.pay(order)
        self.assertEqual(response.status_code, 404)

    def test_a_paid_order_cannot_be_paid_again(self):
        order = self.paid_order(course_id=self.course.pk, price_id=self.price.pk)
        response, _ = self.pay(order)
        self.assertEqual(response.status_code, 422)

    def test_a_failed_order_can_be_retried(self):
        order = self.order(product_id=self.product.pk)
        self.pay(order)
        services.fail_payment(tran_id=order.payments.get().transaction_id)
        response, _ = self.pay(order)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.payments.filter(status=Payment.Status.PENDING).count(), 1)


class CompletePaymentTests(CheckoutTestBase):
    def started(self, **body):
        order = self.order(**body or {'course_id': self.course.pk, 'price_id': self.price.pk})
        self.pay(order)
        return order, order.payments.get()

    def complete(self, payment, **overrides):
        with validation(payment, **overrides):
            return services.complete_payment(tran_id=payment.transaction_id, val_id='VAL-1')

    def test_a_valid_payment_enrols_for_the_prices_validity(self):
        order, payment = self.started()
        self.complete(payment)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        enrolment = Enrollment.objects.get(user=self.student, course=self.course)
        self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)
        # The price is valid for 30 days; this used to enrol forever.
        self.assertAlmostEqual(
            enrolment.valid_till, timezone.now() + timezone.timedelta(days=30), delta=timezone.timedelta(minutes=1)
        )

    def test_the_gateway_details_are_kept(self):
        _, payment = self.started()
        payment = self.complete(payment)
        self.assertEqual((payment.val_id, payment.bank_tran_id, payment.card_type), ('VAL-1', 'BANK-1', 'BKASH-BKash'))

    def test_validated_is_accepted(self):
        _, payment = self.started()
        self.assertEqual(self.complete(payment, status='VALIDATED').status, Payment.Status.SUCCESSFUL)

    def test_a_second_report_changes_nothing(self):
        """The success callback and the IPN both arrive."""
        order, payment = self.started()
        self.complete(payment)
        with patch('apps.billing.services._fulfil') as fulfil:
            self.complete(payment, status='VALIDATED')
        fulfil.assert_not_called()
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_suspicious_payments_are_held_for_an_admin(self):
        cases = {
            'wrong amount': {'currency_amount': '1.00'},
            'wrong currency': {'currency_type': 'USD'},
            'wrong tran_id': {'tran_id': 'someone-else'},
            'risky': {'risk_level': '1'},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                Enrollment.objects.all().delete()
                order, payment = self.started()
                payment = self.complete(payment, **overrides)
                order.refresh_from_db()
                self.assertEqual((payment.status, order.status), (Payment.Status.PENDING, Order.Status.PENDING))
                self.assertTrue(payment.val_id)
                self.assertFalse(Enrollment.objects.exists())
                Order.objects.all().delete()

    def test_an_admin_releases_a_held_payment(self):
        order, payment = self.started()
        payment = self.complete(payment, risk_level='1')
        services.confirm_payment(payment=payment, status=Payment.Status.SUCCESSFUL)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertTrue(Enrollment.objects.filter(course=self.course).exists())

    def test_an_unreported_gateway_payment_cannot_be_confirmed(self):
        _, payment = self.started()
        with self.assertRaises(ValidationError):
            services.confirm_payment(payment=payment, status=Payment.Status.SUCCESSFUL)

    def test_an_invalid_payment_fails(self):
        order, payment = self.started()
        self.assertEqual(self.complete(payment, status='INVALID_TRANSACTION').status, Payment.Status.FAILED)
        self.assertFalse(Enrollment.objects.exists())

    def test_a_late_valid_report_still_settles_a_failed_payment(self):
        order, payment = self.started()
        services.fail_payment(tran_id=payment.transaction_id)
        self.complete(payment)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_a_paid_product_is_listed_as_the_students(self):
        order = self.paid_order(product_id=self.product.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertIn(self.product, selectors.owned_products(self.student))


class CallbackTests(CheckoutTestBase):
    RESULT = 'https://site.test/payment/result'

    def started(self):
        order = self.order(course_id=self.course.pk, price_id=self.price.pk)
        self.pay(order)
        return order, order.payments.get()

    def callback(self, name, **data):
        # Posted as a form, with no token: SSLCommerz sends neither.
        return self.client.post(reverse(f'api:billing:sslcommerz_{name}'), data)

    def test_success_redirects_to_the_result_page(self):
        order, payment = self.started()
        with validation(payment):
            response = self.callback('success', tran_id=payment.transaction_id, val_id='VAL-1', status='VALID')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{self.RESULT}?order_id={order.pk}&status=paid')
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_the_posted_status_is_not_trusted(self):
        """A forged "VALID" is checked with SSLCommerz, which says otherwise."""
        order, payment = self.started()
        with validation(payment, status='INVALID_TRANSACTION'):
            response = self.callback('success', tran_id=payment.transaction_id, val_id='FORGED', status='VALID')
        self.assertIn('status=failed', response['Location'])
        self.assertFalse(Enrollment.objects.exists())

    def test_an_unreachable_validator_says_pending(self):
        order, payment = self.started()
        with patch('apps.billing.sslcommerz.requests.get', side_effect=requests.Timeout):
            response = self.callback('success', tran_id=payment.transaction_id, val_id='VAL-1')
        self.assertIn('status=pending', response['Location'])

    def test_fail_and_cancel(self):
        for name, expected in (('fail', Order.Status.FAILED), ('cancel', Order.Status.CANCELLED)):
            with self.subTest(name):
                order, payment = self.started()
                response = self.callback(name, tran_id=payment.transaction_id)
                self.assertEqual(response.status_code, 302)
                self.assertIn(f'status={"cancelled" if name == "cancel" else "failed"}', response['Location'])
                order.refresh_from_db()
                self.assertEqual(order.status, expected)
                Order.objects.all().delete()

    def test_the_ipn_settles_a_payment(self):
        order, payment = self.started()
        with validation(payment):
            response = self.callback('ipn', tran_id=payment.transaction_id, val_id='VAL-1', status='VALID')
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_an_unknown_transaction_on_the_ipn_is_404(self):
        self.assertEqual(self.callback('ipn', tran_id='nope', val_id='x', status='VALID').status_code, 404)
