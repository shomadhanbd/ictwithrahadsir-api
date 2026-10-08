from django.contrib import admin

from apps.communication.models import Notice, NoticeCategory, SmsMessage
from apps.core.admin import ReadOnlyAdmin, TimestampedAdmin
from apps.core.text.phones import masked_phone


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


@admin.register(Notice)
class NoticeAdmin(TimestampedAdmin):
    list_display = ("id", "title", "created_at")
    list_filter = ("created_at", "categories", "class_levels", "batches")
    search_fields = ("title", "body")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    filter_horizontal = ("categories", "class_levels", "batches")


@admin.register(NoticeCategory)
class NoticeCategoryAdmin(TimestampedAdmin):
    list_display = ("id", "title", "order")
    list_editable = ("order",)
    search_fields = ("title", "slug")
    ordering = ("order", "title")
    prepopulated_fields = {"slug": ("title",)}
