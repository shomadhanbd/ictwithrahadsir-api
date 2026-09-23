"""Exam ownership: any teacher may author, but only their own papers.

`CourseScopedAdminMixin` / `IsCourseTeacher` cannot be reused -- they scope by
`user.teaching`, a `courses.CourseTeacher` row, and a standalone exam has no
course. Ownership here is the `created_by` column.
"""

from rest_framework.exceptions import PermissionDenied

from apps.core.api.permissions import IsTeachingStaff, is_full_admin

MESSAGE = "This exam is not yours to manage."


class IsExamAuthor(IsTeachingStaff):
    """Teaching staff, narrowed to the exams this teacher wrote.

    An admin passes everything. An exam whose author's account was deleted has
    `created_by = NULL`, which no teacher's id matches -- so it falls to admins
    rather than to everyone.
    """

    message = MESSAGE

    def has_object_permission(self, request, view, obj):
        if is_full_admin(request.user):
            return True
        author_id = view.author_id_for(obj)
        return author_id is not None and author_id == request.user.pk


def assert_may_author_exam(request, exam):
    """`IsExamAuthor`'s check, for the paths DRF never runs it on.

    DRF only calls `has_object_permission` from `generics.get_object()`. A POST
    to a *child* collection -- a section, a bulk pick -- fetches no object, so
    without this a teacher could hang a section off another teacher's exam by
    id. Call it from the serializer's `validate()`, and from any `APIView`
    right after it fetches its own row.
    """
    if is_full_admin(request.user):
        return
    if exam is None or exam.created_by_id != request.user.pk:
        raise PermissionDenied(MESSAGE)
