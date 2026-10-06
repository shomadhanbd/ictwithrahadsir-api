from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, F, Max, Q
from django.http import Http404
from django.utils import timezone

from apps.core import providers
from apps.courses.models import Content, ContentCompletion, Course, Enrollment, Section
from apps.identity.roles import is_full_admin, is_teaching_staff


def ordered_course_ids(user, course_ids) -> set:
    """Which of `course_ids` this user has bought."""
    provider = providers.get("courses.ordered_course_ids")
    if provider is None or user is None or not user.is_authenticated:
        return set()
    return provider(user, course_ids)


def course_packages(course_ids) -> dict:
    """The packages each of `course_ids` is sold in. Absent means not for sale."""
    provider = providers.get("courses.course_packages")
    if provider is None or not course_ids:
        return {}
    return provider(course_ids)


def has_students(course) -> bool:
    """Anyone enrolled on, or who has paid for, this course."""
    if Enrollment.objects.filter(course=course).exists():
        return True
    provider = providers.get("courses.sold_course_ids")
    return provider is not None and course.pk in provider([course.pk])


def lesson_exam(content, user):
    """The exam an exam lesson is, as the lesson payload shows it."""
    provider = providers.get("courses.lesson_exam")
    return None if provider is None else provider(content, user)


def admin_lesson_exam(content) -> dict | None:
    """The exam behind an exam lesson, as the admin panel lists it."""
    # `exam` is the exam app's reverse relation, read by name so this app does not import it.
    exam = getattr(content, "exam", None) if content.pk else None
    if exam is None:
        return None
    return {
        "id": exam.pk,
        "slug": exam.slug,
        "status": exam.status,
        "total_marks": exam.total_marks,
        "question_count": sum(section.question_count for section in exam.sections.all()),
    }


def may_manage_course(user, course_id) -> bool:
    """An admin, or a teacher assigned to `course_id`."""
    if is_full_admin(user):
        return True
    return course_id is not None and user.teaching.filter(course_id=course_id).exists()


def is_released(content, now=None) -> bool:
    return content.available_from is None or content.available_from <= (now or timezone.now())


def release_message(content) -> str:
    return f"Available from {timezone.localtime(content.available_from):%d %b %Y, %H:%M}."


def has_current_enrollment(user, course_id) -> bool:
    return Enrollment.objects.filter(course_id=course_id, user=user).current().exists()


def can_open_content(user, content) -> bool:
    """Released, and either free or covered by a current enrolment."""
    if not is_released(content):
        return False
    if not content.paid:
        return True
    if user is None or not user.is_authenticated:
        return False
    return has_current_enrollment(user, content.course_id)


def visible_lessons():
    """Lessons a student can see: active, in an active section under an active parent (or none).

    The one definition the course page, progress, cards and export all count, so 100% is always reachable.
    `lesson_is_visible` asks the same of a single lesson, plus that its course is open.
    """
    return (
        Content.objects.active()
        .filter(section__active=True)
        .filter(Q(section__section__isnull=True) | Q(section__section__active=True))
    )


def lesson_is_visible(content) -> bool:
    """Active, in an active section under an active parent, on a published or archived course.

    A free lesson of a draft course, or one inside a section switched off, is not reachable by its slug.
    """
    section = content.section
    return (
        content.active
        and section.active
        and (section.section_id is None or section.section.active)
        and content.course.status in (Course.Status.PUBLISHED, Course.Status.ARCHIVED)
    )


def accessible_content(user, slug, **filters) -> Content:
    """An active lesson `user` may open; raises 404 or 403 otherwise. Its teachers may preview a draft's."""
    content = Content.objects.select_related("course", "section__section").filter(slug=slug, **filters).first()
    if content is None:
        raise Http404
    signed_in = user is not None and user.is_authenticated
    previewing = content.active and signed_in and may_manage_course(user, content.course_id)
    if not (lesson_is_visible(content) or previewing):
        raise Http404
    if not is_released(content):
        raise PermissionDenied(release_message(content))
    if not previewing and not can_open_content(user, content):
        raise PermissionDenied("Not subscribed")
    return content


def course_for_viewer(user, slug) -> Course:
    """A visible published course; staff may preview any, and enrolled students keep archived ones."""
    courses = Course.objects.filter(slug=slug).with_catalogue_prefetch()
    course = courses.published().visible_to(user).first()
    if not course and user.is_authenticated:
        if is_teaching_staff(user):
            # Preview: a teacher sees their own drafts, not other teachers' unpublished curricula.
            candidate = courses.first()
            course = candidate if candidate and may_manage_course(user, candidate.pk) else None
        else:
            course = courses.available().filter(enrollments__user=user).first()
    if not course:
        raise Http404
    return course


def enrolled_courses(user):
    """Courses the user is enrolled on, archived ones included."""
    course_ids = Enrollment.objects.filter(user=user).values_list("course_id", flat=True)
    return Course.objects.filter(id__in=course_ids).available().with_catalogue_prefetch()


def enrolled_course(user, slug) -> Course:
    """An available course the user currently has access to; raises 404 or 403 otherwise."""
    course = Course.objects.filter(slug=slug).available().first()
    if not course:
        raise Http404
    if not has_current_enrollment(user, course.pk):
        raise PermissionDenied("You are not enrolled on this course.")
    return course


def course_by_slug_or_id(value) -> Course | None:
    if value is None:
        return None
    value = str(value)
    lookup = {"pk": int(value)} if value.isdigit() else {"slug": value}
    return Course.objects.filter(**lookup).first()


def completable_lesson(course, content_id) -> Content:
    """A lesson the student may tick off by hand; exams complete themselves on submit."""
    content = visible_lessons().filter(pk=content_id, course=course).first()
    if not content:
        raise ValidationError({"content_id": ["Unknown content for this course."]})
    if not is_released(content):
        raise ValidationError({"content_id": [release_message(content)]})
    if content.type == Content.Type.EXAM:
        raise ValidationError({"content_id": ["An exam lesson is completed by submitting the exam."]})
    return content


def course_enrollments(course_id):
    return (
        Enrollment.objects.filter(course_id=course_id)
        .select_related("user")
        .prefetch_related("user__groups")
        .order_by("-id")
    )


def progress_percent(completed, total) -> int:
    return round(completed / total * 100) if total else 0


def course_progress(*, user, course) -> dict:
    """Completed lessons out of the course's lessons a student can see."""
    active = visible_lessons().filter(course=course)
    completed = list(
        ContentCompletion.objects.filter(user=user, content__in=active).values_list("content_id", flat=True)
    )
    total = active.count()
    return {
        "completed_content_ids": completed,
        "completed": len(completed),
        "total": total,
        "percent": progress_percent(len(completed), total),
    }


def section_tree(course):
    """A course's active sections and contents, grouped by parent id, in two queries."""
    rows = list(Section.objects.active().filter(course=course))
    sections = defaultdict(list)
    for section in rows:
        sections[section.section_id].append(section)

    contents = defaultdict(list)
    for content in Content.objects.active().filter(section_id__in=[section.pk for section in rows]):
        contents[content.section_id].append(content)
    return sections, contents


def course_card_stats(courses, user=None) -> dict:
    """Per-course aggregates for a page of course cards, in a fixed number of queries."""
    ids = [course.pk for course in courses]

    content_counts = defaultdict(lambda: defaultdict(int))
    # What a student can see on the course page: active lessons in active sections.
    shown = visible_lessons().filter(course_id__in=ids)
    rows = shown.values("course_id", "type").annotate(total=Count("id"))
    for row in rows:
        content_counts[row["course_id"]][row["type"]] = row["total"]

    enrollment_counts = dict(
        Enrollment.objects.filter(course_id__in=ids).values_list("course_id").annotate(total=Count("id"))
    )

    enrollments, ordered = {}, set()
    if ids and user is not None and user.is_authenticated:
        enrollments = {e.course_id: e for e in Enrollment.objects.filter(course_id__in=ids, user=user)}
        ordered = ordered_course_ids(user, ids)

    return {
        "content_counts": content_counts,
        "packages": course_packages(ids),
        "enrollment_counts": enrollment_counts,
        "enrollments": enrollments,
        "ordered": ordered,
    }


def section_siblings(section):
    """The sections sharing `section`'s course and parent, itself included."""
    return Section.objects.filter(course_id=section.course_id, section_id=section.section_id)


def next_section_order(*, course, parent=None) -> int:
    last = Section.objects.filter(course=course, section=parent).aggregate(last=Max("order"))["last"]
    return 0 if last is None else last + 1


def enrollments_due_reminder(*, now=None, days):
    """Access ending within `days`, not yet reminded about this end date."""
    now = now or timezone.now()
    return (
        Enrollment.objects.filter(valid_till__gt=now, valid_till__lte=now + timezone.timedelta(days=days))
        .filter(Q(expiry_reminded_for__isnull=True) | ~Q(expiry_reminded_for=F("valid_till")))
        .select_related("user", "course")
        .order_by("valid_till")
    )


def course_students_export(course) -> list[dict]:
    """Each enrolled student with their access and progress, newest first."""
    active = visible_lessons().filter(course=course)
    total = active.count()
    done = dict(
        ContentCompletion.objects.filter(content__in=active)
        .values("user_id")
        .annotate(n=Count("id"))
        .values_list("user_id", "n")
    )
    return [
        {"enrollment": enrollment, "progress": progress_percent(done.get(enrollment.user_id, 0), total)}
        for enrollment in Enrollment.objects.filter(course=course).select_related("user").order_by("-created_at")
    ]
