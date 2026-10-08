from apps.feedback.models import Feedback
from apps.feedback.validators import validate_course_feedback

# Shown for a student with no name; never their phone number, which would be published.
ANONYMOUS_NAME = "শিক্ষার্থী"


def _designation(user) -> str:
    profile = getattr(user, "student", None)
    if profile is None:
        return ""
    parts = [profile.class_level.name if profile.class_level_id else "", profile.institution]
    return " · ".join(part for part in parts if part)[:150]


def submit_feedback(*, user, course=None, rating, comment) -> Feedback:
    """Writes or rewrites the user's one feedback for `course` (general without); it waits for approval again."""
    if course is not None:
        validate_course_feedback(user=user, course=course)
    feedback, _ = Feedback.objects.update_or_create(
        author=user,
        source=Feedback.Source.COURSE if course else Feedback.Source.GENERAL,
        course=course,
        defaults={
            "rating": rating,
            "comment": comment,
            "name": user.name or ANONYMOUS_NAME,
            "designation": _designation(user),
            "image": user.image,
            "status": Feedback.Status.PENDING,
            "is_featured": False,
        },
    )
    return feedback


def withdraw_feedback(*, user, course=None) -> None:
    source = Feedback.Source.COURSE if course else Feedback.Source.GENERAL
    Feedback.objects.filter(author=user, source=source, course=course).delete()
