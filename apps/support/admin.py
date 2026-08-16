from django.contrib import admin

from apps.support.models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "subject", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("name", "phone", "email", "subject")
    readonly_fields = ("created_at", "updated_at")
