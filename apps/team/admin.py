from django.contrib import admin

from .models import Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "designation", "type", "order"]
    list_filter = ["type"]
    search_fields = ["name"]
