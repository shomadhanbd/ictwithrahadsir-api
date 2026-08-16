from django.contrib import admin

from .models import CourseInstructor, Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "designation", "type", "order"]
    list_filter = ["type"]
    search_fields = ["name"]


@admin.register(CourseInstructor)
class CourseInstructorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "teacher", "course", "type", "commission")
    list_filter = ("type",)
    search_fields = ("name", "email", "phone")
    readonly_fields = ("created_at", "updated_at")
