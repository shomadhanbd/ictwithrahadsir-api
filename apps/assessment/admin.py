from django.contrib import admin

from .models import Exam, ExamAttempt, Question, QuestionBank


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "parent", "order"]
    search_fields = ["title"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["id", "bank", "answer"]
    list_filter = ["bank"]


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ["id", "exam", "user", "marks", "duration"]


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("pk", "content", "mode", "total_marks", "duration_minutes")
    list_filter = ("mode",)
    readonly_fields = ("created_at", "updated_at")
