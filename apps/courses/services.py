import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.core.exceptions import Conflict
from apps.core.sms import get_sms_backend
from apps.courses.models import Content, ContentCompletion, Course, CourseTeacher, Enrollment, Section
from apps.courses.notifications import expiry_reminder
from apps.courses.selectors import (
    completable_lesson,
    enrollments_due_reminder,
    has_students,
    next_section_order,
    section_siblings,
)
from apps.identity.roles import is_full_admin

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


def hand_over_teaching(previous, successor) -> None:
    """Moves `previous`'s course assignments to `successor`, or ends them when there is none."""
    assignments = CourseTeacher.objects.filter(user=previous)
    if successor is None:
        assignments.delete()
        return
    assignments.filter(course__in=CourseTeacher.objects.filter(user=successor).values("course")).delete()
    assignments.update(user=successor)


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


def claim_reminder(enrollment) -> bool:
    """Marks the enrolment reminded about its end date; False if another run already has, so it is texted once."""
    due = Enrollment.objects.filter(pk=enrollment.pk, valid_till=enrollment.valid_till).filter(
        Q(expiry_reminded_for__isnull=True) | ~Q(expiry_reminded_for=enrollment.valid_till)
    )
    return bool(due.update(expiry_reminded_for=enrollment.valid_till))


def release_reminder(enrollment) -> None:
    """Undoes a claim whose text failed, so the next run tries again."""
    Enrollment.objects.filter(pk=enrollment.pk).update(expiry_reminded_for=enrollment.expiry_reminded_for)


def send_expiry_reminders(*, now=None, days=None, dry_run=False) -> int:
    """Texts each student whose access ends soon, once per end date; returns how many were (or would be) sent."""
    sent = 0
    for enrollment in enrollments_due_reminder(now=now, days=days or settings.EXPIRY_REMINDER_DAYS):
        if dry_run:
            sent += 1
            continue
        if not claim_reminder(enrollment):
            continue  # an overlapping run got it first
        if not enrollment.user.phone:
            continue  # nothing to text; claimed so it is not retried every run
        try:
            get_sms_backend().send(enrollment.user.phone, expiry_reminder(enrollment))
        except Exception:
            logger.exception("Expiry reminder failed for enrolment %s", enrollment.pk)
            release_reminder(enrollment)
            continue
        sent += 1
    return sent
