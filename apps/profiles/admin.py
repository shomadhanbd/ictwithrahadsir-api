from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.core.api.permissions import SUPERUSER_ACCOUNT_MESSAGE, may_change_account
from apps.profiles.models import GuardianProfile, StudentProfile, TeacherProfile
from apps.profiles.services import delete_teacher, ensure_teacher_role, release_teacher_account


class GuardianInline(admin.StackedInline):
    model = GuardianProfile
    can_delete = False
    extra = 0


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'designation', 'type', 'institute', 'order')
    list_filter = ('type', 'subjects', 'levels')
    search_fields = ('user__name', 'user__phone', 'designation', 'institute')
    autocomplete_fields = ('user',)
    filter_horizontal = ('subjects', 'levels')

    def save_model(self, request, obj, form, change):
        if not may_change_account(request.user, obj.user):
            raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        previous = TeacherProfile.objects.filter(pk=obj.pk).select_related("user").first() if change else None
        super().save_model(request, obj, form, change)
        ensure_teacher_role(obj)
        if previous is not None and previous.user_id != obj.user_id:
            release_teacher_account(previous.user, successor=obj.user)

    def delete_model(self, request, obj):
        delete_teacher(obj)

    def delete_queryset(self, request, queryset):
        for profile in queryset:
            delete_teacher(profile)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'class_level', 'group', 'institution', 'educational_session')
    list_filter = ('class_level', 'group')
    search_fields = ('user__name', 'user__phone', 'institution')
    autocomplete_fields = ('user', 'class_level', 'group')
    inlines = (GuardianInline,)


@admin.register(GuardianProfile)
class GuardianProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'relation', 'student')
    search_fields = ('name', 'phone', 'student__user__name')
    autocomplete_fields = ('student',)
