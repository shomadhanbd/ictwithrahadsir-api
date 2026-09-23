"""Contract tests for the cart, ordering and manual-payment flow."""

from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.billing.models import Order, Payment
from apps.courses.models import Course, CoursePrice, Enrollment
from apps.identity.models import User
from apps.store.models import Product

ORDER_URL = reverse('api:billing:orders')
PAYMENT_URL = reverse('api:billing:payment_submit')
MY_ORDERS_URL = reverse('api:billing:orders')
FREE_PURCHASE_URL = reverse('api:billing:free_enrollment')
ADMIN_PAYMENT_URL = reverse('api:billing:admin_payment_list')


class ShopTestBase(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(phone='01810400001', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.product = Product.objects.create(name='Digest', slug='digest', price=Decimal('450'), active=True)


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


class PaymentTests(ShopTestBase):
    def setUp(self):
        super().setUp()
        self.course = Course.objects.create(title='ICT', slug='ict', active=True)
        self.order = Order.objects.create(
            user=self.student,
            course=self.course,
            amount=Decimal('1500'),
            total=Decimal('1500'),
        )

    def test_a_payment_is_recorded_as_pending(self):
        response = self.client.post(
            PAYMENT_URL,
            {
                'order_id': self.order.pk,
                'transaction_id': 'TRX1',
                'details': {'vendor': 'bkash', 'sent_from': '0181', 'sent_to': '0171'},
            },
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)

    def test_details_may_arrive_as_a_json_string(self):
        response = self.client.post(
            PAYMENT_URL,
            {
                'order_id': self.order.pk,
                'transaction_id': 'TRX2',
                'details': '{"vendor": "nagad"}',
            },
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.get().vendor, 'nagad')

    def test_malformed_details_are_rejected(self):
        response = self.client.post(
            PAYMENT_URL,
            {'order_id': self.order.pk, 'details': '{not json'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_another_users_order_is_not_payable(self):
        other = User.objects.create_user(phone='01810400003', name='Other', password='Str0ngPass!23')
        auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=other).key}'}
        response = self.client.post(PAYMENT_URL, {'order_id': self.order.pk}, format='json', **auth)
        self.assertEqual(response.status_code, 404)

    def test_the_recorded_amount_comes_from_the_order_not_the_client(self):
        # The client used to be able to record any amount it liked against an
        # order, so a 1,500 course could be "paid" for 1.
        response = self.client.post(
            PAYMENT_URL,
            {'order_id': self.order.pk, 'amount': '1.00', 'transaction_id': 'TAMPER'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.get().amount, Decimal('1500'))

    def test_a_reused_transaction_id_is_refused(self):
        payload = {'order_id': self.order.pk, 'transaction_id': 'TRX-REUSED'}
        self.assertEqual(self.client.post(PAYMENT_URL, payload, format='json', **self.auth).status_code, 201)

        second = self.client.post(PAYMENT_URL, payload, format='json', **self.auth)
        self.assertEqual(second.status_code, 422)
        self.assertIn('transaction_id', second.json()['errors'])
        self.assertEqual(Payment.objects.filter(transaction_id='TRX-REUSED').count(), 1)

    def test_a_transaction_id_cannot_be_reused_by_another_student(self):
        self.client.post(
            PAYMENT_URL,
            {'order_id': self.order.pk, 'transaction_id': 'TRX-SHARED'},
            format='json',
            **self.auth,
        )

        thief = User.objects.create_user(phone='01810400009', name='Thief', password='Str0ngPass!23')
        their_order = Order.objects.create(
            user=thief, course=self.course, amount=Decimal('1500'), total=Decimal('1500')
        )
        auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=thief).key}'}

        response = self.client.post(
            PAYMENT_URL,
            {'order_id': their_order.pk, 'transaction_id': 'TRX-SHARED'},
            format='json',
            **auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_blank_transaction_ids_do_not_collide(self):
        # The constraint is conditional, so several payments may legitimately
        # carry no TrxID at all.
        second_order = Order.objects.create(
            user=self.student,
            course=self.course,
            amount=Decimal('1500'),
            total=Decimal('1500'),
        )
        for order_id in (self.order.pk, second_order.pk):
            response = self.client.post(PAYMENT_URL, {'order_id': order_id}, format='json', **self.auth)
            self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.filter(transaction_id='').count(), 2)

    def test_an_already_paid_order_is_refused(self):
        self.order.status = Order.Status.PAID
        self.order.save(update_fields=['status'])
        response = self.client.post(PAYMENT_URL, {'order_id': self.order.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)


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
        self.payment = Payment.objects.create(order=self.order, amount=Decimal('1500'), transaction_id='TRX')

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


class ProductOrderTests(APITestCase):
    """`Order` has carried `product` and `quantity` from the start; only this
    endpoint never used them, so the store had a cart and no way to check
    out."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone='01710600001',
            name='Buyer',
            password='Str0ngPass!23',
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.user).key}'}
        self.product = Product.objects.create(
            name='ICT Digest',
            price=Decimal('450'),
            stock=10,
            active=True,
        )

    def post(self, **body):
        return self.client.post(ORDER_URL, body, format='json', **self.auth)

    def test_a_product_order_is_created_at_the_list_price(self):
        response = self.post(product_id=self.product.pk)
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.product, self.product)
        self.assertEqual(order.amount, Decimal('450'))
        self.assertEqual(order.total, Decimal('450'))
        self.assertEqual(order.item_title, 'ICT Digest')

    def test_quantity_multiplies_the_total_but_not_the_unit(self):
        response = self.post(product_id=self.product.pk, quantity=3)
        order = Order.objects.get()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(order.quantity, 3)
        self.assertEqual(order.amount, Decimal('450'))
        self.assertEqual(order.total, Decimal('1350'))

    def test_a_live_discount_is_subtracted(self):
        """`discount` is the amount off, the same as CoursePrice."""
        self.product.discount = Decimal('70')
        self.product.discount_till = timezone.now() + timezone.timedelta(days=1)
        self.product.save()
        self.post(product_id=self.product.pk)
        self.assertEqual(Order.objects.get().total, Decimal('380'))

    def test_an_expired_discount_is_ignored(self):
        self.product.discount = Decimal('70')
        self.product.discount_till = timezone.now() - timezone.timedelta(days=1)
        self.product.save()
        self.post(product_id=self.product.pk)
        self.assertEqual(Order.objects.get().total, Decimal('450'))

    def test_ordering_more_than_the_stock_is_rejected(self):
        response = self.post(product_id=self.product.pk, quantity=11)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Order.objects.exists())

    def test_an_inactive_product_is_rejected(self):
        self.product.active = False
        self.product.save()
        self.assertEqual(self.post(product_id=self.product.pk).status_code, 422)

    def test_a_zero_quantity_is_rejected(self):
        self.assertEqual(self.post(product_id=self.product.pk, quantity=0).status_code, 422)

    def test_an_anonymous_visitor_cannot_order(self):
        self.assertEqual(
            self.client.post(ORDER_URL, {'product_id': self.product.pk}, format='json').status_code,
            401,
        )


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
        self.order = Order.objects.create(
            user=self.student,
            course=self.course,
            amount=Decimal('1500'),
            total=Decimal('1500'),
        )
        self.payment = Payment.objects.create(order=self.order, amount=Decimal('1500'), transaction_id='TRX-ATOMIC')

    def test_a_failure_granting_access_rolls_back_the_payment_and_order(self):
        url = reverse('api:billing:admin_payment_update', args=[self.payment.pk])

        failing_grant = patch(
            'apps.billing.services.grant_course_access',
            side_effect=RuntimeError('enrolment backend down'),
        )
        with failing_grant, self.assertRaises(RuntimeError):
            self.client.patch(url, {'status': 'successful'}, format='json', **self.admin_auth)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())


class ProductStockReservationTests(APITestCase):
    """Stock is reserved when the order is placed, not when it is paid.

    Checking stock without reserving it does not stop overselling: two
    requests arriving together read the same figure and both pass.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone='01710600009',
            name='Buyer',
            password='Str0ngPass!23',
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.user).key}'}
        self.product = Product.objects.create(
            name='Limited',
            price=Decimal('100'),
            stock=2,
            active=True,
        )

    def order(self, **body):
        return self.client.post(ORDER_URL, body, format='json', **self.auth)

    def test_placing_an_order_reserves_the_stock(self):
        self.order(product_id=self.product.pk, quantity=2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_stock_cannot_be_sold_twice(self):
        self.assertEqual(self.order(product_id=self.product.pk, quantity=2).status_code, 201)
        # The second buyer sees the reserved figure, not the original one.
        self.assertEqual(self.order(product_id=self.product.pk, quantity=2).status_code, 422)
        self.assertEqual(Order.objects.count(), 1)

    def test_failing_the_payment_gives_the_stock_back(self):
        self.order(product_id=self.product.pk, quantity=2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

        order = Order.objects.get()
        payment = Payment.objects.create(order=order, amount=order.total, transaction_id='TRX-STOCK')
        admin = User.objects.create_user(
            phone='01710600010',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.patch(
            reverse('api:billing:admin_payment_update', args=[payment.pk]),
            {'status': 'failed'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {Token.objects.create(user=admin).key}',
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
