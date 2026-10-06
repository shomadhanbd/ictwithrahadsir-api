from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin
from apps.core.text.phones import masked_phone
from apps.notifications.models import SmsMessage


@admin.register(SmsMessage)
class SmsMessageAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "purpose", "masked", "status", "recipient", "sent_by")
    list_filter = ("purpose", "status", "created_at")
    search_fields = ("phone", "recipient__name")
    list_select_related = ("recipient", "sent_by")
    date_hierarchy = "created_at"

    @admin.display(description="Phone")
    def masked(self, message):
        return masked_phone(message.phone)
