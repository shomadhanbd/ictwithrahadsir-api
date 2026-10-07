from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from apps.academic.models import ClassLevel, Group
from apps.billing.models import Payment, Product
from apps.billing.tests.base import (
    BillingTestBase,
)
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Course, Enrollment
from apps.identity.models import User
from apps.profiles.models import StudentProfile


def course_packages(course_slug, auth=None):
    """The packages the course page offers, as `product_id`s."""
    card = APIClient().get(reverse('api:courses:course_detail', args=[course_slug]), **(auth or {})).json()
    return [package['product_id'] for package in card['packages']]


class ProductTests(BillingTestBase):
    def test_the_course_page_offers_only_products_on_sale(self):
        Product.objects.create(
            product_id=next_slug("product"), title='Retired', price=100, base_price=100, is_active=False
        ).courses.set([self.live])
        Product.objects.create(product_id=next_slug("product"), title='Empty', price=100, base_price=100)
        ended = Product.objects.create(
            product_id=next_slug("product"),
            title='Ended',
            price=100,
            base_price=100,
            access_ends_on=timezone.localdate() - timezone.timedelta(days=1),
        )
        ended.courses.set([self.live])

        self.assertEqual(course_packages('ict-live'), ['hsc-ict'])


class ProductAudienceTests(BillingTestBase):
    """A signed-in student sees only packages whose every course is listed to them."""

    def setUp(self):
        super().setUp()
        self.hsc = ClassLevel.objects.create(name='HSC', slug='hsc')
        self.science = Group.objects.create(name='Science', slug='science')
        self.commerce = Group.objects.create(name='Commerce', slug='commerce')
        Course.objects.filter(pk=self.live.pk).update(class_level=self.hsc)
        Course.objects.filter(pk=self.recorded.pk).update(class_level=self.hsc, group=self.science)

    def product_ids(self, user=None):
        return course_packages('ict-live', bearer(user) if user else None)

    def student_in(self, group):
        student = make_user()
        StudentProfile.objects.update_or_create(user=student, defaults={'class_level': self.hsc, 'group': group})
        return student

    def test_a_package_with_a_course_hidden_from_the_student_is_hidden(self):
        self.assertEqual(self.product_ids(self.student_in(self.commerce)), [])

    def test_a_package_whose_every_course_is_for_the_student_is_shown(self):
        self.assertEqual(self.product_ids(self.student_in(self.science)), ['hsc-ict'])

    def test_a_package_for_a_course_the_student_is_enrolled_on_stays_to_renew_it(self):
        student = self.student_in(self.commerce)
        Enrollment.objects.create(user=student, course=self.recorded)
        self.assertEqual(self.product_ids(student), ['hsc-ict'])

    def test_visitors_see_every_package(self):
        self.assertEqual(self.product_ids(), ['hsc-ict'])


class AdminTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        admin = make_user(role=User.Role.ADMIN)
        self.admin_auth = bearer(admin)

    def post(self, name, body):
        return self.client.post(reverse(name), body, format='json', **self.admin_auth)

    def test_an_admin_creates_a_product(self):
        product = self.post(
            'api:billing:admin_product_list',
            {
                'title': 'Model Tests',
                'product_id': 'model-tests',
                'price': 300,
                'base_price': 400,
                'course_ids': [self.course.pk],
                'access_days': 180,
            },
        )
        self.assertEqual(product.status_code, 201, product.content)
        self.assertEqual(product.json()['product_id'], 'model-tests')

    def test_product_rules(self):
        base = {'title': 'P', 'price': 300, 'base_price': 300, 'course_ids': [self.course.pk]}
        cases = {
            'no course': {**base, 'course_ids': []},
            'base below price': {**base, 'base_price': 200},
            'days and end date': {**base, 'access_days': 30, 'access_ends_on': '2027-01-01'},
            'under the gateway minimum': {**base, 'price': 5, 'base_price': 5},
        }
        for label, body in cases.items():
            with self.subTest(label):
                self.assertEqual(self.post('api:billing:admin_product_list', body).status_code, 422)

    def test_students_are_kept_out(self):
        for url in (reverse('api:billing:admin_payment_list'), reverse('api:billing:admin_product_list')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, **self.auth).status_code, 403)


class EnrollmentDeadlineTests(BillingTestBase):
    def close(self, course, days_ago=1):
        Course.objects.filter(pk=course.pk).update(
            enrollment_deadline=timezone.now() - timezone.timedelta(days=days_ago)
        )

    def test_a_package_stops_selling_after_its_course_closes(self):
        self.close(self.live)
        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('Enrolment for ICT Live Batch closed', str(response.json()['errors']['product_id']))
        create_session.assert_not_called()
        self.assertFalse(Payment.objects.exists())

    def test_a_bundle_stops_selling_when_any_of_its_courses_closes(self):
        self.close(self.recorded)
        self.assertEqual(course_packages('ict-live'), [])

    def test_a_future_deadline_still_sells(self):
        Course.objects.filter(pk=self.live.pk).update(enrollment_deadline=timezone.now() + timezone.timedelta(days=3))
        self.assertEqual(self.started().product, self.product)

    def test_a_closed_course_shows_no_price(self):
        self.close(self.live)
        card = self.client.get(reverse('api:courses:course_detail', args=['ict-live'])).json()
        self.assertIsNone(card['price'])
        self.assertFalse(card['enrollment_open'])


class UnpublishedCourseTests(BillingTestBase):
    def test_a_package_with_a_draft_course_does_not_sell(self):
        Course.objects.filter(pk=self.live.pk).update(status='draft')
        response, create_session = self.initiate(product_id='hsc-ict')
        self.assertEqual(response.status_code, 422)
        self.assertIn('ICT Live Batch is not open for purchase', str(response.json()['errors']['product_id']))
        create_session.assert_not_called()

    def test_an_archived_course_stops_its_packages_selling(self):
        Course.objects.filter(pk=self.recorded.pk).update(status='archived')
        self.assertEqual(course_packages('ict-live'), [])

    def test_a_draft_course_preview_shows_no_price(self):
        Course.objects.filter(pk=self.live.pk).update(status='draft')
        admin = make_user(role=User.Role.ADMIN)
        auth = bearer(admin)
        body = self.client.get(reverse('api:courses:course_detail', args=['ict-live']), **auth).json()
        self.assertEqual(body['status'], 'draft')
        self.assertIsNone(body['price'])


class DiscountEndTests(BillingTestBase):
    def end_discount(self, days=1):
        Product.objects.filter(pk=self.product.pk).update(
            discount_ends_at=timezone.now() - timezone.timedelta(days=days)
        )

    def card_price(self):
        return self.client.get(reverse('api:courses:course_detail', args=['ict-live'])).json()['price']

    def test_a_running_discount_charges_the_price(self):
        Product.objects.filter(pk=self.product.pk).update(discount_ends_at=timezone.now() + timezone.timedelta(days=2))
        self.assertEqual(self.started().amount, 500)
        price = self.card_price()
        self.assertEqual((price['price'], price['base_price']), (500, 600))
        self.assertIsNotNone(price['discount_ends_at'])

    def test_an_ended_discount_charges_the_original_price(self):
        self.end_discount()
        self.assertEqual(self.started().amount, 600)
        price = self.card_price()
        self.assertEqual((price['price'], price['base_price'], price['discount_ends_at']), (600, 600, None))

    def test_the_admin_list_shows_the_effective_price(self):
        self.end_discount()
        auth = bearer(make_user(role=User.Role.ADMIN))
        row = self.client.get(reverse('api:billing:admin_product_list'), **auth).json()['data'][0]
        self.assertEqual((row['price'], row['current_price']), (500, 600))

    def test_cheapest_follows_the_effective_price(self):
        rival = Product.objects.create(product_id=next_slug("product"), title='Year', price=550, base_price=550)
        rival.courses.set([self.live])
        self.end_discount()
        self.assertEqual(self.card_price()['title'], 'Year')

    def test_a_discount_end_needs_a_higher_original_price(self):
        admin = make_user(role=User.Role.ADMIN)
        auth = bearer(admin)
        response = self.client.patch(
            reverse('api:billing:admin_product_detail', args=[self.product.pk]),
            {'base_price': 500, 'discount_ends_at': (timezone.now() + timezone.timedelta(days=1)).isoformat()},
            format='json',
            **auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('discount_ends_at', response.json()['errors'])
