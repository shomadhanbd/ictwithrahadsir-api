from rest_framework.exceptions import PermissionDenied

from apps.core.api.permissions import IsTeachingStaff
from apps.courses.selectors import may_manage_course
from apps.identity.roles import is_full_admin


class IsCourseTeacher(IsTeachingStaff):
    """Teaching staff, limited to their own courses; pair with `CourseScopedAdminMixin` for lists."""

    message = "This course is not yours to manage."

    def has_object_permission(self, request, view, obj):
        return may_manage_course(request.user, view.course_id_for(obj))


class IsCourseTeacherAdminDeletes(IsCourseTeacher):
    """A teacher builds and edits their course's curriculum; deleting part of it, and students' progress with
    it, is an admin's call, as it is for the academic lists."""

    delete_message = "Only an admin may delete part of a course."

    def has_permission(self, request, view):
        if request.method == "DELETE":
            if not is_full_admin(request.user):
                raise PermissionDenied(self.delete_message)
            return True
        return super().has_permission(request, view)


def assert_may_manage_course(request, course_id) -> None:
    """`IsCourseTeacher` for plain views that fetch their own object."""
    if not may_manage_course(request.user, course_id):
        raise PermissionDenied(IsCourseTeacher.message)


class CourseScopedAdminMixin:
    """Limits a course-owned resource to the courses a teacher teaches; `course_field` holds the course id."""

    permission_classes = [IsCourseTeacher]
    course_field = "course_id"

    def course_id_for(self, obj):
        return getattr(obj, self.course_field, None)

    def _assert_may_write(self, serializer):
        """A write may only land in a course the caller manages, including one it is moved to."""
        if self.course_field == "id":
            return
        course = serializer.validated_data.get("course", getattr(serializer.instance, "course", None))
        assert_may_manage_course(self.request, course.pk if course else None)

    def perform_create(self, serializer):
        self._assert_may_write(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._assert_may_write(serializer)
        super().perform_update(serializer)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if is_full_admin(user):
            return queryset
        return queryset.filter(**{f"{self.course_field}__in": user.teaching.values_list("course_id", flat=True)})
