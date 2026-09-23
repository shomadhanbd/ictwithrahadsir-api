"""Pieces of the courses API that both audiences build on."""

from rest_framework.views import APIView

from apps.core.api.permissions import (
    IsTeachingStaff,
    assert_may_manage_course,
)
from apps.core.api.viewsets import (
    CourseScopedAdminMixin,  # noqa: F401
)
from apps.courses.models import (
    Course,
)


class BaseCourseEnrollmentAPIView(APIView):
    """The admin panel identifies a course by `slugOrId` on the enrolment
    endpoints -- either the numeric id or the slug, never `course_id`."""

    permission_classes = [IsTeachingStaff]

    def get_course(self, data):
        value = data.get('slugOrId') or data.get('course_id')
        if value is None:
            return None
        value = str(value)
        if value.isdigit():
            course = Course.objects.filter(pk=int(value)).first()
        else:
            course = Course.objects.filter(slug=value).first()
        if course is not None:
            # Enrolling somebody grants paid access, so it is scoped the same
            # way editing the course is.
            assert_may_manage_course(self.request, course.pk)
        return course
