"""Course-side operations other apps are allowed to call.

Granting access to a course is a `courses` concern, but it is triggered
from several places -- an admin attaching a student, a free claim, and a
confirmed payment over in `billing`. Those sites each
wrote `Enrollment` directly, which is how `billing` ended up reaching into
another app's tables.

Routing them through here gives the write one owner and makes the
dependency direction explicit: billing depends on courses, never the
reverse.
"""

from django.utils import timezone

from apps.courses.models import CoursePrice, Enrollment


def grant_course_access(*, user, course, payment_type, valid_till=None):
    """Enrol `user` on `course`, or update an existing enrolment."""
    enrollment, _ = Enrollment.objects.update_or_create(
        course=course,
        user=user,
        defaults={'valid_till': valid_till, 'payment_type': payment_type},
    )
    return enrollment


def access_until(price):
    """When access bought at `price` ends; None for forever.

    A price's validity is an absolute cut-off date, or a relative number of
    days (none meaning forever).
    """
    if price.validity_type == CoursePrice.ValidityType.ABSOLUTE:
        return price.validity_time
    if price.validity_duration:
        return timezone.now() + timezone.timedelta(days=price.validity_duration)
    return None


def grant_from_price(*, user, course, price):
    """Enrol against a specific price, deriving validity from its own rule.

    An admin's choice, so it is applied as given, even when it is shorter than
    what the student had.
    """
    payment_type = Enrollment.PaymentType.FREE if price is None or price.amount == 0 else Enrollment.PaymentType.PAID
    valid_till = access_until(price) if price is not None else None
    return grant_course_access(user=user, course=course, payment_type=payment_type, valid_till=valid_till)


def grant_purchased_access(*, user, course, valid_till):
    """Enrol `user` on a course they paid for, until `valid_till` (None: forever).

    Never shortens access they already have: buying a 30-day bundle must not
    cut a lifetime enrolment down to 30 days. The later end wins.
    """
    existing = Enrollment.objects.filter(course=course, user=user).first()
    if existing is not None:
        if existing.valid_till is None or valid_till is None:
            valid_till = None
        else:
            valid_till = max(existing.valid_till, valid_till)
    return grant_course_access(
        user=user, course=course, payment_type=Enrollment.PaymentType.PAID, valid_till=valid_till
    )


def revoke_course_access(*, user_id, course) -> bool:
    """Remove an enrolment. Returns whether anything was removed."""
    deleted, _ = Enrollment.objects.filter(course=course, user_id=user_id).delete()
    return deleted > 0
