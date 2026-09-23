"""Contract tests for the product catalogue and the basket."""

from decimal import Decimal

from django.urls import reverse

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.identity.models import User
from apps.store.models import CartItem, Product

PRODUCTS_URL = reverse('api:store:product_list')
CART_URL = reverse('api:store:cart')
CART_ITEMS_URL = reverse('api:store:cart_item_add')


class StoreTestBase(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(phone='01810400001', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.product = Product.objects.create(name='Digest', slug='digest', price=Decimal('450'), active=True)


class ProductCatalogueTests(StoreTestBase):
    def test_products_are_public_and_paginated(self):
        body = self.client.get(PRODUCTS_URL).json()
        self.assertEqual(body['meta']['total'], 1)

    def test_inactive_products_are_hidden(self):
        Product.objects.create(name='Retired', slug='retired', price=Decimal('10'), active=False)
        self.assertEqual(self.client.get(PRODUCTS_URL).json()['meta']['total'], 1)


class CartTests(StoreTestBase):
    def item_url(self):
        return reverse('api:store:cart_item_detail', args=[self.product.pk])

    def test_cart_requires_authentication(self):
        self.assertEqual(self.client.get(CART_URL).status_code, 401)

    def test_adding_a_product_returns_the_whole_cart(self):
        response = self.client.post(CART_ITEMS_URL, {'product_id': self.product.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_adding_the_same_product_twice_increments_quantity(self):
        for _ in range(2):
            self.client.post(CART_ITEMS_URL, {'product_id': self.product.pk}, format='json', **self.auth)
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_an_unknown_product_is_rejected(self):
        response = self.client.post(CART_ITEMS_URL, {'product_id': 999999}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_increment_and_decrement(self):
        self.client.post(CART_ITEMS_URL, {'product_id': self.product.pk}, format='json', **self.auth)

        self.client.patch(self.item_url(), {'action': 'increment'}, format='json', **self.auth)
        self.assertEqual(CartItem.objects.get().quantity, 2)

        self.client.patch(self.item_url(), {'action': 'decrement'}, format='json', **self.auth)
        self.assertEqual(CartItem.objects.get().quantity, 1)

    def test_decrementing_to_zero_removes_the_item(self):
        self.client.post(CART_ITEMS_URL, {'product_id': self.product.pk}, format='json', **self.auth)
        self.client.patch(self.item_url(), {'action': 'decrement'}, format='json', **self.auth)
        self.assertFalse(CartItem.objects.exists())

    def test_an_unknown_action_is_rejected(self):
        self.client.post(CART_ITEMS_URL, {'product_id': self.product.pk}, format='json', **self.auth)
        response = self.client.patch(self.item_url(), {'action': 'sideways'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_acting_on_an_item_not_in_the_cart_is_404(self):
        response = self.client.patch(self.item_url(), {'action': 'increment'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_delete_empties_the_line(self):
        self.client.post(CART_ITEMS_URL, {'product_id': self.product.pk}, format='json', **self.auth)
        self.assertEqual(self.client.delete(self.item_url(), **self.auth).status_code, 200)
        self.assertFalse(CartItem.objects.exists())


class ProductSlugTests(APITestCase):
    """Product slugs come from the shared `apps.core.slugs.unique_slug`.

    `store` used to carry its own copy of that function, whose only real
    difference was the fallback it passed. These pin the behaviour that
    copy had, so consolidating on the shared one cannot change a slug.
    """

    def make(self, name):
        return Product.objects.create(name=name, price=Decimal('1')).slug

    def test_repeated_names_are_numbered_from_two(self):
        self.assertEqual(
            [self.make('ICT Digest') for _ in range(3)],
            ['ict-digest', 'ict-digest-2', 'ict-digest-3'],
        )

    def test_an_unsluggable_name_falls_back_to_product(self):
        """Not "item", which is the shared helper's own default."""
        self.assertEqual(self.make('!!!'), 'product')

    def test_a_bengali_name_is_transliterated(self):
        self.assertEqual(self.make('আইসিটি বই'), 'aisiti-bai')

    def test_an_explicit_slug_is_left_alone(self):
        product = Product.objects.create(name='Anything', slug='chosen-by-hand', price=Decimal('1'))
        self.assertEqual(product.slug, 'chosen-by-hand')


class ProductQuerySetTests(APITestCase):
    def setUp(self):
        self.live = Product.objects.create(name='Live', price=Decimal('1'), active=True)
        self.hidden = Product.objects.create(name='Hidden', price=Decimal('1'), active=False)
        self.featured = Product.objects.create(name='Featured', price=Decimal('1'), active=True, featured=True, stock=3)

    def test_active_excludes_hidden_products(self):
        self.assertNotIn(self.hidden, Product.objects.active())
        self.assertIn(self.live, Product.objects.active())

    def test_featured_and_in_stock_compose(self):
        self.assertEqual(list(Product.objects.active().featured().in_stock()), [self.featured])
