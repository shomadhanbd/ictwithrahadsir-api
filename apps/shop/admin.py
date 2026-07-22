from django.contrib import admin

from .models import CartItem, Order, Payment, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "price", "stock", "active", "is_book"]
    list_filter = ["active", "is_book", "featured"]
    search_fields = ["name", "sku", "barcode"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "item_title", "amount", "status", "created_at"]
    list_filter = ["status"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "amount", "vendor", "status", "created_at"]
    list_filter = ["vendor", "status"]


admin.site.register(CartItem)
