"""Notices, static pages and the homepage furniture."""

from django.contrib import admin

from apps.core.admin import TimestampedAdmin

from .models import Advertisement, EBook, Notice, NoticeCategory, Page, Testimonial


@admin.register(Notice)
class NoticeAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'created_at')
    list_filter = ('created_at', 'categories')
    search_fields = ('title', 'slug', 'body')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('categories',)


@admin.register(NoticeCategory)
class NoticeCategoryAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'notice_category', 'order')
    list_editable = ('order',)
    search_fields = ('title', 'slug')
    ordering = ('order', 'title')
    list_select_related = ('notice_category',)
    autocomplete_fields = ('notice_category',)
    prepopulated_fields = {'slug': ('title',)}


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


@admin.register(EBook)
class EBookAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'created_at')
    search_fields = ('title', 'description')
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
    readonly_fields = ('key', 'slug', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
