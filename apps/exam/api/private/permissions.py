from apps.core.api.auth.permissions import IsTeachingStaff
from apps.exam.selectors import AUTHOR_MESSAGE, may_author_exam


class IsExamAuthor(IsTeachingStaff):
    """Teaching staff, narrowed to exams they wrote or that belong to a course they teach."""

    message = AUTHOR_MESSAGE

    def has_object_permission(self, request, view, obj):
        return may_author_exam(request.user, view.exam_for(obj))
