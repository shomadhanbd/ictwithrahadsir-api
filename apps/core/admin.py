"""Django admin branding and shared ModelAdmin bases."""

from django.contrib import admin

admin.site.site_header = "Shomadhan Coaching — back office"
admin.site.site_title = "Shomadhan Coaching"
admin.site.index_title = "Data and diagnostics"


class TimestampedAdmin(admin.ModelAdmin):
    """For `TimestampModel` subclasses: the timestamps are set automatically."""

    readonly_fields = ("created_at", "updated_at")


class ReadOnlyAdmin(admin.ModelAdmin):
    """For rows only the application writes (OTPs, lesson completions): view and delete, never add or edit."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
