"""The catalogue: courses, their section/content tree, prices and enrolments.

Every list here sets `list_select_related` for the columns it renders and
`autocomplete_fields` for its foreign keys. Both matter more than they look:
without the first, a changelist runs a query per row just to print a name;
without the second, every edit form renders a `<select>` containing every
row of the target table, which is fine at seed size and unusable once there
are fifty thousand students.
"""

from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin import ReadOnlyAdmin, TimestampedAdmin

from .models import (
    Content,
    ContentCompletion,
    Coupon,
    Course,
    CourseCategory,
    CourseMaterial,
    CoursePrice,
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
    list_display = ('id', 'title', 'is_online', 'active', 'featured', 'enrolled', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'prices_link')
    list_display_links = ('id', 'title')
    # The two flags that get toggled most, editable straight from the list.
    list_editable = ('active', 'featured')
    list_filter = ('is_online', 'active', 'featured', 'created_at')
    search_fields = ('title', 'subtitle', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('-created_at',)
    filter_horizontal = ('categories',)
    inlines = [SectionInline]

    @admin.display(description='Enrolled', ordering='_enrolled')
    def enrolled(self, course):
        # Reads the annotation from get_queryset, not a fresh COUNT per row.
        return course._enrolled

    @admin.display(description='Prices')
    def prices_link(self, course):
        """A link to this course's prices, since they cannot be inlined.

        `CoursePrice` addresses its subject through `priceable_type` /
        `priceable_id` rather than a foreign key, so Django cannot build an
        inline for it (admin.E202). A filtered link is the next best thing
        and saves copying an id between two screens.
        """
        if not course.pk:
            return '-'
        url = (
            f'{reverse("admin:courses_courseprice_changelist")}'
            f'?priceable_type__exact={CoursePrice.PRICEABLE_COURSE}'
            f'&q={course.pk}'
        )
        return format_html('<a href="{}">View prices for this course</a>', url)

    def get_queryset(self, request):
        # `enrolled` would otherwise be a COUNT per row on the changelist.
        return super().get_queryset(request).annotate(_enrolled=Count('enrollments', distinct=True))


@admin.register(CourseCategory)
class CourseCategoryAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'category', 'order')
    list_editable = ('order',)
    search_fields = ('title', 'slug')
    ordering = ('order', 'title')
    list_select_related = ('category',)
    autocomplete_fields = ('category',)
    prepopulated_fields = {'slug': ('title',)}


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
    # Needed so `Content.section` can use an autocomplete widget.
    search_fields = ('title', 'slug', 'course__title')
    ordering = ('course', 'order')
    list_select_related = ('course', 'section')
    autocomplete_fields = ('course', 'section')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ContentInline]


@admin.register(Content)
class ContentAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'course', 'section', 'type', 'paid', 'active', 'order')
    list_editable = ('paid', 'active', 'order')
    list_filter = ('type', 'paid', 'active', 'course')
    search_fields = ('title', 'slug', 'course__title')
    ordering = ('course', 'order')
    list_select_related = ('course', 'section')
    autocomplete_fields = ('course', 'section')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(CoursePrice)
class CoursePriceAdmin(TimestampedAdmin):
    list_display = ('id', 'priceable_type', 'subject', 'title', 'amount', 'discount', 'type')
    list_filter = ('priceable_type', 'type', 'validity_type')
    search_fields = ('title',)
    ordering = ('-id',)

    @admin.display(description='Subject')
    def subject(self, price):
        """The course this price belongs to.

        `Course` is reached through `priceable_id`, not a foreign key, so
        this cannot be `select_related` -- it is one query per row. Acceptable
        on a list that is short and rarely opened; if the store ever becomes
        priceable too, this wants a proper relation instead.
        """
        course = price.course
        return course.title if course else f'#{price.priceable_id}'


@admin.register(Coupon)
class CouponAdmin(TimestampedAdmin):
    list_display = ('id', 'code', 'price', 'discount', 'discount_type', 'valid_till')
    list_filter = ('discount_type', 'valid_till')
    search_fields = ('code',)
    ordering = ('-id',)
    list_select_related = ('price',)
    autocomplete_fields = ('price',)


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
    # "Why can this student not open the lesson?" starts with their phone.
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
        """Whether this enrolment currently grants access.

        The same rule the API applies (`EnrollmentQuerySet.current`), shown
        here because "expired two days ago" is the answer to most access
        complaints and is otherwise a date the reader has to compare by eye.
        """
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
    """Written by the course player when a student ticks a lesson.

    Read-only: editing these by hand desynchronises a student's progress bar
    from what they actually did, and the resulting report is never "my
    progress is wrong", it is "the course is broken".
    """

    list_display = ('id', 'user', 'content', 'course', 'created_at')
    list_filter = ('course', 'created_at')
    search_fields = ('user__name', 'user__phone', 'content__title', 'course__title')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'content', 'course')
