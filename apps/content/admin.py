from django.contrib import admin

from .models import Advertisement, CourseMaterial, ContactMessage, EBook, Notice, NoticeCategory, Page, Testimonial


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "created_at"]
    search_fields = ["title"]


@admin.register(NoticeCategory)
class NoticeCategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "notice_category", "order"]


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "designation", "ratings"]


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "type"]


@admin.register(EBook)
class EBookAdmin(admin.ModelAdmin):
    list_display = ["id", "title"]


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "course", "type"]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "subject", "is_read", "created_at"]
    list_filter = ["is_read"]


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ["id", "key", "value_type"]

