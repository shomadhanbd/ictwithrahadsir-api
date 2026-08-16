"""Course-side operations other apps are allowed to call.

Granting access to a course is a `courses` concern, but it is triggered
from several places -- an admin attaching a student, a bulk import, a free
claim, and a confirmed payment over in `billing`. Those four sites each
wrote `CourseUser` directly, which is how `billing` ended up reaching into
another app's tables.

Routing them through here gives the write one owner and makes the
dependency direction explicit: billing depends on courses, never the
reverse.
"""

from django.utils import timezone

from apps.courses.models import CoursePrice, CourseUser


def grant_course_access(*, user, course, payment_type, valid_till=None):
    """Enrol `user` on `course`, or update an existing enrolment."""
    enrollment, _ = CourseUser.objects.update_or_create(
        course=course,
        user=user,
        defaults={'valid_till': valid_till, 'payment_type': payment_type},
    )
    return enrollment


def grant_from_price(*, user, course, price):
    """Enrol against a specific price, deriving validity from its own rule.

    `CoursePrice` carries the validity policy -- an absolute cut-off date or
    a relative number of days -- so callers do not have to reimplement it.
    """
    payment_type = (
        CourseUser.PaymentType.FREE
        if price is None or price.amount == 0
        else CourseUser.PaymentType.PAID
    )

    valid_till = None
    if price is not None:
        if price.validity_type == CoursePrice.ValidityType.ABSOLUTE:
            valid_till = price.validity_time
        elif price.validity_duration:
            valid_till = timezone.now() + timezone.timedelta(days=price.validity_duration)

    return grant_course_access(
        user=user, course=course, payment_type=payment_type, valid_till=valid_till
    )


def revoke_course_access(*, user_id, course) -> bool:
    """Remove an enrolment. Returns whether anything was removed."""
    deleted, _ = CourseUser.objects.filter(course=course, user_id=user_id).delete()
    return deleted > 0
