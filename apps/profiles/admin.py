from django.contrib import admin

from apps.profiles.models import GuardianProfile, StudentProfile, TeacherProfile
from apps.profiles.services import ensure_teacher_role


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
        super().save_model(request, obj, form, change)
        # The same call the API makes; without it the account cannot reach the
        # courses it is assigned to.
        ensure_teacher_role(obj)


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
