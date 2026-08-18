"""The product catalogue and customers' baskets."""

from django.contrib import admin
from django.utils.html import format_html

from apps.core.admin import TimestampedAdmin
from apps.store.models import CartItem, Product


@admin.register(Product)
class ProductAdmin(TimestampedAdmin):
    list_display = ('id', 'name', 'price', 'discount', 'stock_level', 'active', 'featured', 'created_at')
    list_editable = ('active', 'featured')
    list_filter = ('active', 'is_book', 'featured', 'created_at')
    search_fields = ('name', 'slug', 'sku', 'barcode')
    ordering = ('order', '-created_at')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('categories',)

    @admin.display(description='Stock', ordering='stock')
    def stock_level(self, product):
        """Stock is reserved when an order is placed, so a low figure here is
        the thing that starts rejecting checkouts."""
        if product.stock == 0:
            return format_html('<span style="color:#b32d2e;font-weight:600">out of stock</span>')
        if product.stock < 5:
            return format_html('<span style="color:#b36b00">{}</span>', product.stock)
        return product.stock


@admin.register(CartItem)
class CartItemAdmin(TimestampedAdmin):
    list_display = ('id', 'user', 'product', 'quantity', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__name', 'user__phone', 'product__name')
    ordering = ('-created_at',)
    list_select_related = ('user', 'product')
    autocomplete_fields = ('user', 'product')
