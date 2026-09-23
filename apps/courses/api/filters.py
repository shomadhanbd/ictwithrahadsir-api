"""Query-parameter filters for the admin course endpoints.

`DjangoFilterBackend` has been a default backend since the project was set
up, but nothing declared a filterset, so every list view hand-rolled the same
"read a query param, conditionally `.filter()`" block in `get_queryset`.
Declaring them keeps the accepted parameters visible at the top of the view
instead of buried in an override, and means an unrecognised parameter is
ignored in one place rather than eight.

Two behaviours deliberately stay in `get_queryset` rather than moving here,
because they depend on the *action* and not on a query parameter: the
category and section trees show only top-level rows when listing, so the
admin panel can expand them lazily. A filterset cannot see `self.action`.
"""

from django_filters import rest_framework as filters

from apps.courses.models import (
    Content,
    Coupon,
    CourseMaterial,
    CoursePrice,
    CourseTeacher,
    Routine,
    Section,
)


class CoursePriceFilter(filters.FilterSet):
    priceable_type = filters.CharFilter()
    #: The panel filters a course's prices with
    #: `?priceable_type=course&course_id=<id>`, where `course_id` means "the
    #: priceable_id, given the priceable_type is course".
    course_id = filters.NumberFilter(method='filter_course')

    class Meta:
        model = CoursePrice
        fields = ['priceable_type', 'course_id']

    def filter_course(self, queryset, name, value):
        return queryset.filter(priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=value)


class CouponFilter(filters.FilterSet):
    price_id = filters.NumberFilter(field_name='price_id')

    class Meta:
        model = Coupon
        fields = ['price_id']


class RoutineFilter(filters.FilterSet):
    course_id = filters.NumberFilter(field_name='course_id')

    class Meta:
        model = Routine
        fields = ['course_id']


class SectionFilter(filters.FilterSet):
    course_id = filters.NumberFilter(field_name='course_id')
    section_id = filters.NumberFilter(field_name='section_id')

    class Meta:
        model = Section
        fields = ['course_id', 'section_id']


class ContentFilter(filters.FilterSet):
    section_id = filters.NumberFilter(field_name='section_id')

    class Meta:
        model = Content
        fields = ['section_id']


class CourseMaterialFilter(filters.FilterSet):
    course_id = filters.NumberFilter(field_name='course_id')

    class Meta:
        model = CourseMaterial
        fields = ['course_id']


class CourseTeacherFilter(filters.FilterSet):
    """The panel's course-teacher table is always scoped to one course."""

    course_id = filters.NumberFilter(field_name='course_id')

    class Meta:
        model = CourseTeacher
        fields = ['course_id']
