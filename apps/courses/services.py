"""Course-side operations other apps are allowed to call.

Granting access to a course is a `courses` concern, but it is triggered
from several places -- an admin attaching a student, a bulk import, a free
claim, and a confirmed payment over in `billing`. Those four sites each
wrote `Enrollment` directly, which is how `billing` ended up reaching into
another app's tables.

Routing them through here gives the write one owner and makes the
dependency direction explicit: billing depends on courses, never the
reverse.
"""

from django.db import transaction
from django.utils import timezone

from apps.core.spreadsheets import text
from apps.courses.models import CoursePrice, Enrollment
from apps.identity.models import User


def grant_course_access(*, user, course, payment_type, valid_till=None):
    """Enrol `user` on `course`, or update an existing enrolment."""
    enrollment, _ = Enrollment.objects.update_or_create(
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
        Enrollment.PaymentType.FREE
        if price is None or price.amount == 0
        else Enrollment.PaymentType.PAID
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
    deleted, _ = Enrollment.objects.filter(course=course, user_id=user_id).delete()
    return deleted > 0


@transaction.atomic
def import_enrollments(*, course, records) -> dict:
    """Bulk-enrol existing students on a course from parsed spreadsheet rows.

    Returns `{attached, missing}`. A phone that matches no account is counted
    as missing rather than creating one -- this screen attaches people who
    have already registered, and silently inventing accounts from a
    spreadsheet typo is not a thing an admin can undo.

    The roster is loaded once instead of one `User` lookup per row. The
    sibling importer in `identity` already did this; this one did not, so a
    sheet of 500 students cost 500 extra queries and, with no transaction
    around it, a failure halfway left half the class enrolled.
    """
    phones = {text(record, 'phone') for record in records}
    phones.discard('')
    users_by_phone = {
        user.phone: user
        for user in User.objects.filter(phone__in=phones)
    }

    attached, missing = 0, 0
    for record in records:
        user = users_by_phone.get(text(record, 'phone'))
        if not user:
            missing += 1
            continue

        grant_course_access(
            user=user, course=course, payment_type=Enrollment.PaymentType.FREE
        )
        attached += 1

    return {'attached': attached, 'missing': missing}
