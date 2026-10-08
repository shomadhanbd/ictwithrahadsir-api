from django.contrib import admin

from apps.core.admin import TimestampedAdmin
from apps.feedback.models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(TimestampedAdmin):
    list_display = ("id", "name", "source", "course", "rating", "status", "is_featured", "created_at")
    list_filter = ("source", "status", "is_featured", "rating")
    list_editable = ("status", "is_featured")
    search_fields = ("name", "comment", "course__title")
    list_select_related = ("course",)
    raw_id_fields = ("author", "course")
