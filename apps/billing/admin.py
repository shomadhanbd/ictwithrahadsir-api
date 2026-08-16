from django.contrib import admin

from apps.billing.models import Order, Payment


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "item_title", "amount", "status", "created_at"]
    list_filter = ["status"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "amount", "vendor", "status", "created_at"]
    list_filter = ["vendor", "status"]
