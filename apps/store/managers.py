"""Querysets for the catalogue and the basket.

`filter(active=True)` was written out at three separate sites, and the two
prefetches below are what stand between a product listing and a query per
row for its categories -- easy to forget at a new call site, and invisible
when you do.
"""

from django.db import models


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)

    def featured(self):
        return self.filter(featured=True)

    def in_stock(self):
        return self.filter(stock__gt=0)

    def with_categories(self):
        """Preload the m2m the product payload always renders."""
        return self.prefetch_related('categories')


class CartItemQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def with_product(self):
        """Preload the nested product and its categories.

        The cart payload renders both, so without this a basket costs two
        extra queries per line.
        """
        return self.select_related('product').prefetch_related('product__categories')
