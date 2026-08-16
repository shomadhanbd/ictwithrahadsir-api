from django.contrib import admin

from .models import Exam, ExamResult, McqQuestion, McqStore


@admin.register(McqStore)
class McqStoreAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "mcq_store", "order"]
    search_fields = ["title"]


@admin.register(McqQuestion)
class McqQuestionAdmin(admin.ModelAdmin):
    list_display = ["id", "mcq_store", "answer"]
    list_filter = ["mcq_store"]


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ["id", "exam", "user", "marks", "duration"]


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("pk", "content", "mode", "total_marks", "duration_minutes")
    list_filter = ("mode",)
    readonly_fields = ("created_at", "updated_at")
