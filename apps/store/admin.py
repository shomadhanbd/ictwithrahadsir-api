from django.contrib import admin

from apps.store.models import CartItem, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "price", "stock", "active", "created_at")
    list_filter = ("active", "is_book", "featured")
    search_fields = ("name", "sku", "barcode")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "quantity", "created_at")
    readonly_fields = ("created_at", "updated_at")
