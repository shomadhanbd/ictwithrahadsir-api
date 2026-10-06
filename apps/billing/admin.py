from django.contrib import admin

from apps.billing.models import Payment, Product
from apps.billing.services.offline import mark_payment_paid
from apps.core.admin import TimestampedAdmin


@admin.register(Product)
class ProductAdmin(TimestampedAdmin):
    list_display = ['id', 'product_id', 'title', 'price', 'base_price', 'is_active']
    list_filter = ['is_active', 'courses']
    search_fields = ['product_id', 'title']
    filter_horizontal = ['courses']
    ordering = ['id']


@admin.register(Payment)
class PaymentAdmin(TimestampedAdmin):
    list_display = [
        'id',
        'transaction_id',
        'user',
        'product',
        'amount',
        'status',
        'transaction_date',
        'created_at',
    ]
    list_filter = ['status', 'refund_due']
    search_fields = ['transaction_id', 'user__phone']
    list_select_related = ['user', 'product']
    raw_id_fields = ['user', 'product']
    readonly_fields = [
        'transaction_id',
        'gateway_response',
        'gateway_page_url',
        'refund_due',
        *TimestampedAdmin.readonly_fields,
    ]
    # Editing these would bypass access granting; a stuck payment is settled with the action below.
    settled_fields = ['user', 'product', 'amount', 'access_until', 'status', 'method']
    actions = ['mark_paid']

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return [*fields, *self.settled_fields] if obj is not None else fields

    @admin.action(description='Mark paid and grant access (check the SSLCommerz panel first)')
    def mark_paid(self, request, queryset):
        marked = [mark_payment_paid(payment, by=request.user) for payment in queryset]
        paid = [payment for payment in marked if payment is not None]
        duplicates = sum(1 for payment in paid if payment.refund_due)
        skipped = len(marked) - len(paid)
        self.message_user(
            request,
            f'{len(paid) - duplicates} marked paid with access granted; {duplicates} duplicate(s) noted for refund; '
            f'{skipped} skipped (already paid, or the account is gone).',
        )
