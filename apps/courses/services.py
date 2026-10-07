import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.core.exceptions import Conflict
from apps.courses.models import Content, ContentCompletion, Course, CourseTeacher, Enrollment, Section
from apps.courses.notifications import access_ended, expiry_reminder
from apps.courses.selectors import (
    completable_lesson,
    enrollments_due_ended_notice,
    enrollments_due_reminder,
    has_students,
    next_section_order,
    section_siblings,
)
from apps.identity.roles import is_full_admin
from apps.notifications.gateways import SmsError
from apps.notifications.models import SmsMessage
from apps.notifications.services import send_sms

logger = logging.getLogger("courses")

TOGGLEABLE_FLAGS = ("active", "paid")


@transaction.atomic
def create_course(data, *, by) -> Course:
    course = Course.objects.create(**data)
    # A teacher only sees courses they teach, so the one they create is assigned to them.
    if not is_full_admin(by):
        add_course_teacher(course=course, user=by)
    return course


def delete_course(course) -> None:
    if has_students(course):
        raise Conflict("Students are enrolled in this course. Archive it instead.")
    course.delete()


def create_section(data) -> Section:
    data = dict(data)
    data.setdefault("order", next_section_order(course=data["course"], parent=data.get("section")))
    return Section.objects.create(**data)


def toggle_content_flag(content: Content, flag: str) -> Content:
    setattr(content, flag, not getattr(content, flag))
    content.save(update_fields=[flag, "updated_at"])
    return content


def complete_lesson(*, user, content):
    ContentCompletion.objects.get_or_create(user=user, content=content)


def complete_lesson_by_hand(*, user, course, content_id):
    complete_lesson(user=user, content=completable_lesson(course, content_id))


def uncomplete_lesson(*, user, course, content_id) -> None:
    ContentCompletion.objects.filter(user=user, course=course, content_id=content_id).exclude(
        content__type=Content.Type.EXAM
    ).delete()


def end_teaching(user) -> None:
    """Removes every course assignment of an account that is no longer a teacher's."""
    CourseTeacher.objects.filter(user=user).delete()


def add_course_teacher(*, course, user):
    return CourseTeacher.objects.get_or_create(course=course, user=user)[0]


def grant_course_access(*, user, course, payment_type, valid_till=None):
    """Enrol `user` on `course`, or update an existing enrolment."""
    enrollment, _ = Enrollment.objects.update_or_create(
        course=course,
        user=user,
        defaults={"valid_till": valid_till, "payment_type": payment_type},
    )
    return enrollment


def grant_purchased_access(*, user, course, valid_till):
    """Enrol a buyer; never shortens access they already have."""
    existing = Enrollment.objects.filter(course=course, user=user).first()
    if existing is not None:
        if existing.valid_till is None or valid_till is None:
            valid_till = None
        else:
            valid_till = max(existing.valid_till, valid_till)
    return grant_course_access(
        user=user, course=course, payment_type=Enrollment.PaymentType.PAID, valid_till=valid_till
    )


def update_enrollment(enrollment, data) -> Enrollment:
    for field in ("valid_till", "payment_type"):
        if field in data:
            setattr(enrollment, field, data[field])
    enrollment.save()
    return enrollment


def revoke_course_access(*, user_id, course) -> bool:
    """Remove an enrolment. Returns whether anything was removed."""
    deleted, _ = Enrollment.objects.filter(course=course, user_id=user_id).delete()
    return deleted > 0


@transaction.atomic
def move_section(section, *, direction) -> None:
    """Swaps a section with its neighbour above or below, renumbering the siblings 0..n."""
    siblings = list(section_siblings(section).select_for_update().order_by("order", "id"))
    index = next(i for i, s in enumerate(siblings) if s.pk == section.pk)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(siblings):
        siblings[index], siblings[target] = siblings[target], siblings[index]
    for order, sibling in enumerate(siblings):
        if sibling.order != order:
            sibling.order = order
            sibling.save(update_fields=["order", "updated_at"])


def _claim(enrollment, field) -> bool:
    """Marks the enrolment texted about its end date in `field`; False if another run already has, so it goes once."""
    due = Enrollment.objects.filter(pk=enrollment.pk, valid_till=enrollment.valid_till).filter(
        Q(**{f"{field}__isnull": True}) | ~Q(**{field: enrollment.valid_till})
    )
    return bool(due.update(**{field: enrollment.valid_till}))


def _release(enrollment, field) -> None:
    """Undoes a claim whose text failed, so the next run tries again."""
    Enrollment.objects.filter(pk=enrollment.pk).update(**{field: getattr(enrollment, field)})


def _text_each(enrollments, *, field, message, purpose, dry_run) -> int:
    """Texts each enrolment once per end date; returns how many were (or would be) sent."""
    sent = 0
    for enrollment in enrollments:
        if dry_run:
            sent += 1
            continue
        if not _claim(enrollment, field):
            continue  # an overlapping run got it first
        if not enrollment.user.phone:
            continue  # nothing to text; claimed so it is not retried every run
        try:
            send_sms(enrollment.user.phone, message(enrollment), purpose=purpose, recipient=enrollment.user)
        except SmsError:
            logger.warning("%s text failed for enrolment %s", purpose, enrollment.pk)
            _release(enrollment, field)
            continue
        sent += 1
    return sent


def send_expiry_reminders(*, now=None, days=None, dry_run=False) -> int:
    """Texts each student whose access ends soon, once per end date."""
    return _text_each(
        enrollments_due_reminder(now=now, days=days or settings.EXPIRY_REMINDER_DAYS),
        field="expiry_reminded_for",
        message=expiry_reminder,
        purpose=SmsMessage.Purpose.EXPIRY_REMINDER,
        dry_run=dry_run,
    )


def send_access_ended_notices(*, now=None, dry_run=False) -> int:
    """Texts each student whose access has just ended, once per end date."""
    return _text_each(
        enrollments_due_ended_notice(now=now, days=settings.ACCESS_ENDED_NOTICE_DAYS),
        field="expiry_notice_sent_for",
        message=access_ended,
        purpose=SmsMessage.Purpose.ACCESS_ENDED,
        dry_run=dry_run,
    )
