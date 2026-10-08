from django.conf import settings
from django.utils import timezone

from apps.core.text.phones import normalize_phone
from apps.identity.models import OTP, LoginFailure, User
from apps.identity.roles import is_full_admin

ALL = "all"


# Users, for the admin user API


def account_detail_queryset(viewer):
    """Every account the viewer may see, with the role and student profile loaded."""
    users = User.objects.prefetch_related("groups").select_related("student")
    return _visible_to(viewer, users)


def roster(viewer, *, role=None, status=None):
    """The admin user list. `status` is "active" (the default), "inactive" or "all"; `role` may be "all" too."""
    users = account_detail_queryset(viewer)

    if role and role != ALL:
        users = users.filter(groups__name=role)

    if status == "inactive":
        users = users.filter(is_active=False)
    elif status != ALL:
        users = users.filter(is_active=True)

    return users


def search_students(viewer, term, *, limit):
    """Active students matching `term`. A teacher also finds any student whose full phone number they type."""
    students = User.objects.students().filter(is_active=True)

    found = _visible_to(viewer, students)
    if term:
        found = found.search(term)

    phone = normalize_phone(term)
    if phone:
        found = found | students.filter(phone=phone)

    return found[:limit]


def _visible_to(viewer, users):
    """Admins see every account; a teacher sees only students enrolled, now or before, on a course they teach."""
    if is_full_admin(viewer):
        return users
    own_students = User.objects.students().filter(course_enrollments__course__instructors__user=viewer).values("pk")
    return users.filter(pk__in=own_students)


# Sign in


def account_state(phone) -> dict:
    """Whether `phone` has an account, and whether it signs in with a password."""
    user = User.objects.filter(phone=phone).only("password").first()
    return {"user_exist": bool(user), "password_exist": bool(user and user.has_usable_password())}


# One-time codes


def seconds_until_resend(phone) -> int:
    """0 if a code may be sent to `phone` now, otherwise how many seconds to wait."""
    now = timezone.now()
    one_hour_ago = now - timezone.timedelta(hours=1)
    last_hour = OTP.objects.filter(phone=phone, created_at__gte=one_hour_ago).order_by("created_at")
    wait = 0

    newest = last_hour.last()
    if newest and settings.OTP_RESEND_COOLDOWN_SECONDS:
        cooldown_ends = newest.created_at + timezone.timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
        wait = max(wait, int((cooldown_ends - now).total_seconds()))

    cap = settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR
    if cap and last_hour.count() >= cap:
        oldest_drops_out = last_hour.first().created_at + timezone.timedelta(hours=1)
        wait = max(wait, int((oldest_drops_out - now).total_seconds()))

    return wait


def seconds_until_login(phone) -> int:
    """0 if `phone` may try its password now, otherwise how many seconds its lockout has left."""
    window_start = timezone.now() - timezone.timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    recent = list(
        LoginFailure.objects.filter(phone=phone, created_at__gte=window_start)
        .order_by("-created_at")
        .values_list("created_at", flat=True)[: settings.LOGIN_MAX_FAILURES]
    )
    if len(recent) < settings.LOGIN_MAX_FAILURES:
        return 0
    unlocks = recent[-1] + timezone.timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    return max(int((unlocks - timezone.now()).total_seconds()), 1)
