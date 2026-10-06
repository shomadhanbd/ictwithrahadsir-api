from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.billing.models import Product
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import (
    Course,
)
from apps.identity.models import User

COURSE_LIST_URL = reverse('api:courses:course_list')


class CoursePackagePricingTests(APITestCase):
    """A course's price is whatever billing packages it is sold in."""

    def setUp(self):
        self.course = Course.objects.create(title='Physics', slug='physics', status='published')

    def package(self, **fields):
        fields.setdefault('base_price', fields.get('price', 0))
        fields.setdefault("product_id", next_slug("package"))
        package = Product.objects.create(**fields)
        package.courses.add(self.course)
        return package

    def card(self):
        return self.client.get(COURSE_LIST_URL).json()['data'][0]

    def test_a_course_in_no_package_is_not_for_sale(self):
        card = self.card()
        self.assertIsNone(card['price'])
        self.assertFalse(card['is_free'])

    def test_price_is_the_cheapest_package_on_sale(self):
        self.package(title='Year', price=1500, base_price=2000, access_days=365)
        self.package(title='Month', price=300, access_days=30)
        self.package(title='Old', price=100, is_active=False)
        self.package(title='Expired', price=50, access_ends_on=timezone.localdate() - timezone.timedelta(days=1))
        price = self.card()['price']
        self.assertEqual((price['title'], price['price'], price['access_days']), ('Month', 300, 30))

    def test_a_zero_taka_package_makes_it_free(self):
        self.package(title='Free', price=0)
        self.assertTrue(self.card()['is_free'])

    def test_detail_lists_every_package_and_marks_bundles(self):
        other = Course.objects.create(title='Chemistry', slug='chemistry', status='published')
        bundle = self.package(title='Science bundle', price=2500)
        bundle.courses.add(other)
        self.package(title='Physics only', price=1500)
        body = self.client.get(reverse('api:courses:course_detail', args=['physics'])).json()
        self.assertEqual(
            [(p['title'], p['course_count']) for p in body['packages']],
            [('Physics only', 1), ('Science bundle', 2)],
        )

    def test_packages_cost_one_query_for_a_whole_page(self):
        for i in range(5):
            course = Course.objects.create(title=f'C{i}', slug=f'c{i}', status='published')
            Product.objects.create(
                product_id=next_slug("product"), title=f'P{i}', price=100, base_price=100
            ).courses.add(course)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(COURSE_LIST_URL)
        product_queries = [q for q in ctx.captured_queries if 'billing_product' in q['sql']]
        self.assertEqual(len(product_queries), 1)


class AdminProductFilterTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)

    def test_lists_the_packages_that_include_a_course(self):
        physics = Course.objects.create(title='Physics', slug='physics')
        chemistry = Course.objects.create(title='Chemistry', slug='chemistry')
        Product.objects.create(product_id=next_slug("product"), title='Physics', price=100, base_price=100).courses.add(
            physics
        )
        Product.objects.create(product_id=next_slug("product"), title='Bundle', price=200, base_price=200).courses.add(
            physics, chemistry
        )
        Product.objects.create(
            product_id=next_slug("product"), title='Chemistry', price=100, base_price=100
        ).courses.add(chemistry)
        body = self.client.get(reverse('api:billing:admin_product_list'), {'course_id': physics.pk}, **self.auth).json()
        self.assertEqual(sorted(p['title'] for p in body['data']), ['Bundle', 'Physics'])
        bundle = next(p for p in body['data'] if p['title'] == 'Bundle')
        self.assertEqual(sorted(bundle['course_ids']), sorted([physics.pk, chemistry.pk]))
        self.assertEqual(bundle['payment_count'], 0)

    def test_filters_bundles_from_single_course_prices(self):
        physics = Course.objects.create(title='Physics', slug='physics')
        chemistry = Course.objects.create(title='Chemistry', slug='chemistry')
        Product.objects.create(product_id=next_slug("product"), title='Physics', price=100, base_price=100).courses.add(
            physics
        )
        Product.objects.create(product_id=next_slug("product"), title='Bundle', price=200, base_price=200).courses.add(
            physics, chemistry
        )
        url = reverse('api:billing:admin_product_list')
        for kind, expected in (('bundle', ['Bundle']), ('single', ['Physics'])):
            body = self.client.get(url, {'kind': kind}, **self.auth).json()
            self.assertEqual([p['title'] for p in body['data']], expected, kind)
