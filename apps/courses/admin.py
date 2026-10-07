from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin import ReadOnlyAdmin, TimestampedAdmin

from .models import (
    Content,
    ContentCompletion,
    Course,
    CourseMaterial,
    Enrollment,
    Routine,
    Section,
)


class SectionInline(admin.TabularInline):
    model = Section
    fk_name = 'course'
    extra = 0
    fields = ('title', 'order', 'active')
    show_change_link = True


@admin.register(Course)
class CourseAdmin(TimestampedAdmin):
    list_display = (
        'id',
        'title',
        'status',
        'class_level',
        'group',
        'batch',
        'delivery',
        'is_featured',
        'enrolled',
        'created_at',
    )
    readonly_fields = ('published_at', 'packages_link', *TimestampedAdmin.readonly_fields)
    list_display_links = ('id', 'title')
    list_editable = ('status', 'is_featured')
    list_filter = (
        'status',
        'class_level',
        'group',
        'batch',
        'delivery',
        'difficulty',
        'language',
        'is_online',
        'is_featured',
        'created_at',
    )
    list_select_related = ('class_level', 'group', 'batch')
    autocomplete_fields = ('class_level', 'group', 'batch')
    search_fields = ('title', 'subtitle', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('title', 'subtitle', 'slug', 'summary', 'description')}),
        (
            'Publishing',
            {'fields': ('status', 'published_at', 'is_featured', 'fake_student_count', 'packages_link')},
        ),
        ('Format', {'fields': ('delivery', 'is_online', 'difficulty', 'language', 'duration')}),
        ('Audience', {'fields': ('class_level', 'group', 'batch')}),
        ('Schedule', {'fields': ('starts_on', 'ends_on', 'enrollment_deadline', 'schedule_note')}),
        ('Media', {'fields': ('thumbnail', 'banner', 'promo_video', 'syllabus_pdf')}),
        (
            'Landing page',
            {'fields': ('learning_outcomes', 'target_audience', 'requirements', 'highlights', 'faqs')},
        ),
        ('SEO', {'classes': ('collapse',), 'fields': ('meta_title', 'meta_description', 'og_image')}),
        ('Timestamps', {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )
    inlines = [SectionInline]

    @admin.display(description='Enrolled', ordering='enrolled_count')
    def enrolled(self, course):
        return course.enrolled_count

    @admin.display(description='Packages')
    def packages_link(self, course):
        if not course.pk:
            return '-'
        url = f'{reverse("admin:billing_product_changelist")}?courses__id__exact={course.pk}'
        return format_html('<a href="{}">Packages that include this course</a>', url)

    def get_queryset(self, request):
        return super().get_queryset(request).with_enrolled_count()


class ContentInline(admin.TabularInline):
    model = Content
    fk_name = 'section'
    extra = 0
    fields = ('title', 'type', 'order', 'paid', 'active')
    show_change_link = True


@admin.register(Section)
class SectionAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'course', 'section', 'order', 'active')
    list_editable = ('order', 'active')
    list_filter = ('active', 'course')
    search_fields = ('title', 'course__title')
    ordering = ('course', 'order')
    list_select_related = ('course', 'section')
    autocomplete_fields = ('course', 'section')
    inlines = [ContentInline]


@admin.register(Content)
class ContentAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'course', 'section', 'type', 'paid', 'active', 'order')
    list_editable = ('paid', 'active', 'order')
    list_filter = ('type', 'paid', 'active', 'course')
    search_fields = ('title', 'course__title')
    ordering = ('course', 'order')
    list_select_related = ('course', 'section')
    autocomplete_fields = ('course', 'section')


@admin.register(Routine)
class RoutineAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'course')
    search_fields = ('title', 'course__title')
    ordering = ('-id',)
    list_select_related = ('course',)
    autocomplete_fields = ('course',)


@admin.register(Enrollment)
class EnrollmentAdmin(TimestampedAdmin):
    list_display = ('id', 'student', 'course', 'payment_type', 'valid_till', 'status')
    list_filter = ('payment_type', 'valid_till', 'course')
    search_fields = (
        'user__name',
        'user__phone',
        'user__email',
        'course__title',
        'course__slug',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'course')
    autocomplete_fields = ('user', 'course')

    @admin.display(description='Student', ordering='user__name')
    def student(self, enrollment):
        user = enrollment.user
        return f'{user.name or "-"} ({user.phone or user.email or "-"})'

    @admin.display(description='Access', boolean=True)
    def status(self, enrollment):
        return enrollment.is_current


@admin.register(CourseMaterial)
class CourseMaterialAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'type', 'course', 'created_at')
    list_filter = ('type', 'course')
    search_fields = ('title', 'course__title')
    ordering = ('-created_at',)
    list_select_related = ('course',)
    autocomplete_fields = ('course',)


@admin.register(ContentCompletion)
class ContentCompletionAdmin(ReadOnlyAdmin):
    """Read-only: completions are written by the course player."""

    list_display = ('id', 'user', 'content', 'course', 'created_at')
    list_filter = ('course', 'created_at')
    search_fields = ('user__name', 'user__phone', 'content__title', 'course__title')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'content', 'course')
