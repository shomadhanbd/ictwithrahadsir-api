from django.contrib import admin

from .models import ExamResult, McqQuestion, McqStore


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
    list_display = ["id", "content", "user", "marks", "duration"]
