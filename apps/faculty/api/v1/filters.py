"""Query-parameter filters for the faculty endpoints."""

from django_filters import rest_framework as filters

from apps.faculty.models import CourseInstructor


class InstructorFilter(filters.FilterSet):
    course_id = filters.NumberFilter(field_name='course_id')

    class Meta:
        model = CourseInstructor
        fields = ['course_id']
