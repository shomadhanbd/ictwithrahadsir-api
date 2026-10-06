from django.conf import settings
from django.utils import timezone

from apps.core.text.phones import normalize_phone
from apps.identity.models import OTP, User
from apps.identity.roles import is_full_admin

ANY = "all"


def users_visible_to(viewer, users):
    """Admins see every account; a teacher sees only students enrolled, now or before, on a course they teach."""
    if is_full_admin(viewer):
        return users
    own_students = User.objects.students().filter(course_enrollments__course__instructors__user=viewer).values("pk")
    return users.filter(pk__in=own_students)


def roster(viewer, *, role=None, status=None):
    """The admin user list; `status` defaults to active, and `"all"` skips a filter."""
    users = User.objects.registered().prefetch_related("groups").select_related("student__guardian")
    users = users_visible_to(viewer, users)
    if role and role != ANY:
        users = users.filter(groups__name=role)
    if status == "inactive":
        users = users.filter(is_active=False)
    elif status != ANY:
        users = users.filter(is_active=True)
    return users


def account_detail_queryset(viewer):
    return users_visible_to(viewer, User.objects.prefetch_related("groups").select_related("student__guardian"))


def search_students(viewer, term, *, limit):
    """Admins search every student; a teacher searches their own, or finds any other by full phone number."""
    students = User.objects.students().filter(is_active=True)
    if is_full_admin(viewer):
        return (students.search(term) if term else students)[:limit]
    found = users_visible_to(viewer, students)
    if term:
        found = found.search(term)
    phone = normalize_phone(term)
    if phone:
        found = found | students.filter(phone=phone)
    return found[:limit]


def seconds_until_resend(phone) -> int:
    """0 if a code may be sent now, otherwise how long to wait."""
    now = timezone.now()
    recent = OTP.objects.filter(phone=phone, created_at__gte=now - timezone.timedelta(hours=1)).order_by("created_at")

    waits = [0]
    newest = recent.last()
    if newest and settings.OTP_RESEND_COOLDOWN_SECONDS:
        elapsed = (now - newest.created_at).total_seconds()
        waits.append(int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed))

    cap = settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR
    if cap and recent.count() >= cap:
        waits.append(int(3600 - (now - recent.first().created_at).total_seconds()))

    return max(waits)
