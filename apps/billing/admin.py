"""Orders and payments.

The important thing here is that confirming a payment is not a field edit.
It moves the payment, moves its order, and grants the student access to the
course -- three writes across two apps that `apps/billing/services.py`
performs in one transaction. Saving `status = successful` on the model does
only the first, so the platform takes the money and enrols nobody, with
nothing in the UI to suggest anything is wrong.

So `status` is not editable on the form. It is changed through the two
actions below, which call the service.
"""

from django.contrib import admin, messages
from django.utils.html import format_html

from rest_framework.exceptions import ValidationError

from apps.billing.models import Order, Payment
from apps.billing.services import confirm_payment
from apps.core.admin import TimestampedAdmin


class PaymentInline(admin.TabularInline):
    """An order's payments, on the order page.

    Chasing a disputed transfer otherwise means opening the payment list and
    filtering it by an order id copied off another screen.
    """

    model = Payment
    extra = 0
    fields = ('transaction_id', 'amount', 'vendor', 'status', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(Order)
class OrderAdmin(TimestampedAdmin):
    list_display = ('id', 'user', 'item_title', 'amount', 'total', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    # An order is looked up by who placed it far more often than by its id,
    # and the phone number is what a student quotes on the phone.
    search_fields = (
        'id', 'item_title', 'user__name', 'user__phone', 'user__email',
        'payments__transaction_id',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    # `user` is rendered on every row; without this the changelist runs one
    # query per order just to print a name.
    list_select_related = ('user',)
    autocomplete_fields = ('user', 'course', 'price', 'product')
    inlines = [PaymentInline]

    def get_search_results(self, request, queryset, search_term):
        # Searching a reverse relation can multiply rows.
        queryset, _ = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), False


@admin.register(Payment)
class PaymentAdmin(TimestampedAdmin):
    list_display = (
        'id', 'transaction_id', 'payer', 'amount', 'order_amount',
        'vendor', 'status', 'created_at',
    )
    list_filter = ('status', 'vendor', 'created_at')
    search_fields = (
        'transaction_id', 'order__id',
        'order__user__name', 'order__user__phone', 'order__user__email',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_select_related = ('order', 'order__user')
    autocomplete_fields = ('order',)
    actions = ('confirm_payments', 'fail_payments')

    #: Set through the actions, never on the form -- see the module docstring.
    readonly_fields = ('status', 'created_at', 'updated_at')

    @admin.display(description='Payer', ordering='order__user__name')
    def payer(self, payment):
        user = payment.order.user
        return f'{user.name or "-"} ({user.phone or user.email or "-"})'

    @admin.display(description='Order total')
    def order_amount(self, payment):
        """Flagged when it disagrees with the payment.

        A payment recording less than its order is the shape a part payment
        takes, and also the shape a mistake takes. Either way the reviewer
        should see it before confirming, not after.
        """
        if payment.amount != payment.order.amount:
            return format_html(
                '<span style="color:#b32d2e;font-weight:600">{}</span>', payment.order.amount
            )
        return payment.order.amount

    def _apply(self, request, queryset, status, verb):
        done = 0
        for payment in queryset.select_related('order', 'order__user'):
            try:
                confirm_payment(payment=payment, status=status)
            except ValidationError as exc:
                self.message_user(
                    request,
                    f'Payment #{payment.pk} skipped: {exc.detail}',
                    level=messages.ERROR,
                )
                continue
            done += 1
        if done:
            self.message_user(request, f'{done} payment(s) {verb}.', level=messages.SUCCESS)

    @admin.action(description='Confirm payment — marks the order paid and grants course access')
    def confirm_payments(self, request, queryset):
        self._apply(request, queryset, Payment.Status.SUCCESSFUL, 'confirmed')

    @admin.action(description='Mark payment failed — fails the order and returns any reserved stock')
    def fail_payments(self, request, queryset):
        self._apply(request, queryset, Payment.Status.FAILED, 'marked failed')
