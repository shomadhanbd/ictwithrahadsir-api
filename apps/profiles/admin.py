from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.core.api.auth.permissions import SUPERUSER_ACCOUNT_MESSAGE, may_change_account
from apps.profiles.models import StudentProfile, TeacherProfile
from apps.profiles.services import delete_teacher, ensure_teacher_role


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "designation", "type", "institute", "order")
    list_filter = ("type", "subjects", "levels")
    search_fields = ("user__name", "user__phone", "designation", "institute")
    autocomplete_fields = ("user",)
    filter_horizontal = ("subjects", "levels")

    def get_readonly_fields(self, request, obj=None):
        # A teacher keeps the account they were created with.
        return ("user",) if obj else ()

    def save_model(self, request, obj, form, change):
        if not may_change_account(request.user, obj.user):
            raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        super().save_model(request, obj, form, change)
        ensure_teacher_role(obj)

    def delete_model(self, request, obj):
        if not may_change_account(request.user, obj.user):
            raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        delete_teacher(obj)

    def delete_queryset(self, request, queryset):
        profiles = list(queryset.select_related("user"))
        # Check the whole selection first so a refusal never leaves it half-deleted.
        for profile in profiles:
            if not may_change_account(request.user, profile.user):
                raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        for profile in profiles:
            delete_teacher(profile)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "class_level", "group", "institution", "guardian_name", "guardian_phone")
    list_filter = ("class_level", "group")
    search_fields = ("user__name", "user__phone", "institution", "guardian_name", "guardian_phone")
    autocomplete_fields = ("user", "class_level", "group")
