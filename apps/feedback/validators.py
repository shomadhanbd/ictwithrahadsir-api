from django.core.exceptions import ValidationError

from apps.courses.models import Enrollment
from apps.feedback.models import Feedback


def validate_course_feedback(*, user, course):
    """Students who are or were enrolled may rate a course."""
    if not Enrollment.objects.filter(user=user, course=course).exists():
        raise ValidationError({"course": "Only students of this course can give it feedback."})


def validate_feedback(*, source, course, status, is_featured):
    if source == Feedback.Source.COURSE and course is None:
        raise ValidationError({"course_id": "Choose the course this feedback is about."})
    if source != Feedback.Source.COURSE and course is not None:
        raise ValidationError({"course_id": "Only course feedback names a course."})
    if is_featured and status != Feedback.Status.APPROVED:
        raise ValidationError({"is_featured": "Approve the feedback before featuring it."})
