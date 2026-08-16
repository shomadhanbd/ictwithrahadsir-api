from django.contrib import admin

from .models import Content, Course, CourseCategory, CoursePrice, CourseUser, Coupon, Routine, Section, CourseMaterial


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ["title", "order", "active"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "is_online", "active", "featured", "created_at"]
    list_filter = ["is_online", "active", "featured"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SectionInline]


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "category", "order"]
    search_fields = ["title"]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "course", "section", "order", "active"]
    list_filter = ["active"]


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "course", "section", "type", "paid", "active", "order"]
    list_filter = ["type", "paid", "active"]
    search_fields = ["title"]


@admin.register(CoursePrice)
class CoursePriceAdmin(admin.ModelAdmin):
    list_display = ["id", "course", "title", "amount", "discount", "type"]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["id", "code", "price", "discount", "discount_type", "valid_till"]


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "course"]


@admin.register(CourseUser)
class CourseUserAdmin(admin.ModelAdmin):
    list_display = ["id", "course", "user", "payment_type", "valid_till"]
    list_filter = ["payment_type"]


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "type", "course", "created_at")
    search_fields = ("title",)
    readonly_fields = ("created_at", "updated_at")
