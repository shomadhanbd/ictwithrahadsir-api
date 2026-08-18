"""The teacher roster and their per-course assignments."""

from django.contrib import admin

from apps.core.admin import TimestampedAdmin

from .models import CourseInstructor, Teacher


class CourseInstructorInline(admin.TabularInline):
    """A teacher's course assignments, on the teacher page."""

    model = CourseInstructor
    extra = 0
    fields = ('course', 'designation', 'type', 'commission', 'order')
    autocomplete_fields = ('course',)
    show_change_link = True


@admin.register(Teacher)
class TeacherAdmin(TimestampedAdmin):
    """Editing a teacher here propagates to their assignments.

    `apps/faculty/signals.py` pushes a changed name, designation, description
    or image onto every `CourseInstructor` that had not overridden it, so a
    rename reaches the course pages instead of only this row.
    """

    list_display = ('id', 'name', 'designation', 'type', 'order', 'assignment_count')
    list_editable = ('order',)
    list_filter = ('type',)
    search_fields = ('name', 'designation')
    ordering = ('order', '-created_at')
    inlines = [CourseInstructorInline]

    @admin.display(description='Courses')
    def assignment_count(self, teacher):
        return teacher.assignments.count()

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_assignments=Count('assignments'))


@admin.register(CourseInstructor)
class CourseInstructorAdmin(TimestampedAdmin):
    list_display = ('id', 'name', 'teacher', 'course', 'type', 'commission', 'order')
    list_editable = ('order',)
    list_filter = ('type', 'course')
    search_fields = ('name', 'email', 'phone', 'teacher__name', 'course__title')
    ordering = ('order', '-created_at')
    list_select_related = ('teacher', 'course')
    autocomplete_fields = ('teacher', 'course', 'user')
    fieldsets = (
        (None, {'fields': ('teacher', 'course', 'user', 'order', 'commission')}),
        (
            'Per-course overrides',
            {
                'description': (
                    'Left blank, these are filled from the linked teacher on save '
                    'and kept in step afterwards. Set one to bill this teacher '
                    'differently on this course only.'
                ),
                'fields': ('name', 'designation', 'description', 'type', 'image'),
            },
        ),
        ('Contact', {'fields': ('email', 'phone', 'institute')}),
        ('Timestamps', {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )
