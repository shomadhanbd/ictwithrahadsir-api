"""Static pages and the homepage furniture."""

from django.contrib import admin

from apps.core.admin import TimestampedAdmin

from .models import Advertisement, Page, Testimonial


@admin.register(Testimonial)
class TestimonialAdmin(TimestampedAdmin):
    list_display = ('id', 'name', 'designation', 'ratings')
    list_filter = ('ratings',)
    search_fields = ('name', 'designation', 'description')
    ordering = ('-created_at',)


@admin.register(Advertisement)
class AdvertisementAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'type')
    list_filter = ('type',)
    search_fields = ('title',)
    ordering = ('-created_at',)


@admin.register(Page)
class PageAdmin(TimestampedAdmin):
    """Seeded rows that are only ever edited, never created or deleted.

    The homepage counters and banner are `Page` rows rather than a dedicated
    model, so `key` is what the frontend looks them up by -- renaming one
    silently empties a section of the landing page.
    """

    list_display = ('id', 'key', 'value_type', 'value')
    list_filter = ('value_type',)
    search_fields = ('key', 'slug', 'value')
    ordering = ('key',)
    readonly_fields = ('key', 'slug', *TimestampedAdmin.readonly_fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
