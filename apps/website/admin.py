from django.contrib import admin

from apps.core.admin import TimestampedAdmin
from apps.website.models import Banner, Section


@admin.register(Section)
class SectionAdmin(TimestampedAdmin):
    list_display = ("key", "is_visible", "updated_at")
    list_filter = ("is_visible",)
    search_fields = ("key",)
    # Edited in the admin panel, where the content is checked against its fields.
    readonly_fields = ("key", "content", *TimestampedAdmin.readonly_fields)


@admin.register(Banner)
class BannerAdmin(TimestampedAdmin):
    list_display = ("title", "order", "is_active", "starts_at", "ends_at")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title",)
