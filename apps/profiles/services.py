from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core import providers
from apps.profiles.models import GuardianProfile, StudentProfile, TeacherProfile

TEACHER_ROLE = "teacher"


def ensure_teacher_role(profile) -> None:
    """Give a teacher's account the `teacher` role, unless an admin or moderator would be demoted."""
    user = profile.user
    if user is None or user.has_role("admin", "moderator"):
        return
    user.set_role(TEACHER_ROLE)


def release_teacher_account(user, *, successor=None) -> None:
    """An account that is no longer a teacher's: its course assignments pass to `successor`, or end, and it
    loses the teacher role. An admin's or moderator's own role is left alone."""
    if user is None:
        return
    hand_over = providers.get("profiles.hand_over_teaching")  # courses sits above this app
    if hand_over is not None:
        hand_over(user, successor)
    user.groups.remove(*user.groups.filter(name=TEACHER_ROLE))
    user.__dict__.pop("role", None)


def save_student_profile(user, data) -> None:
    """Writes the nested `student` block; `guardian` arrives nested as `{"guardian": {...}}`."""
    if data is None:
        return
    data = dict(data)
    guardian = data.pop("guardian", None)
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    GuardianProfile.objects.update_or_create(student=profile, defaults=guardian or {})
    user.student = profile  # replaces a stale `select_related` copy


def ensure_student_profile(user, *, institution=None, educational_session=None, class_level=None, group=None):
    """A student profile with a blank guardian row, filled with whatever sign-up gave."""
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    if institution is not None:
        profile.institution = institution
    if educational_session is not None:
        profile.educational_session = educational_session
    if class_level is not None:
        profile.class_level = class_level
        profile.group = group
    profile.save()
    GuardianProfile.objects.get_or_create(student=profile)
    return profile


@transaction.atomic
def create_teacher(data) -> TeacherProfile:
    data = dict(data)
    user = _resolve_teacher_user(data.pop("user", None), current=None)
    subjects, levels = data.pop("subjects", None), data.pop("levels", None)
    profile = TeacherProfile.objects.create(user=user, **data)
    _set_taxonomies(profile, subjects, levels)
    ensure_teacher_role(profile)
    return profile


@transaction.atomic
def update_teacher(profile, data) -> TeacherProfile:
    data = dict(data)
    previous = profile.user
    user = _resolve_teacher_user(data.pop("user", None), current=profile.user)
    if user is not None:
        profile.user = user
    subjects, levels = data.pop("subjects", None), data.pop("levels", None)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    _set_taxonomies(profile, subjects, levels)
    ensure_teacher_role(profile)
    if previous is not None and previous.pk != profile.user_id:
        release_teacher_account(previous, successor=profile.user)
    return profile


@transaction.atomic
def delete_teacher(profile) -> None:
    release_teacher_account(profile.user)
    profile.delete()


def _resolve_teacher_user(user_data, *, current):
    """`user_data` is an account (from `user_id`), a dict of account fields, or None."""
    if user_data is None:
        if current is None:
            raise ValidationError({"user_id": ["An account is required."]})
        return None
    if not isinstance(user_data, dict):
        if user_data != current and user_data.has_role("student"):
            raise ValidationError(
                {"user_id": ["That account is a student's. Give the teacher an account of their own."]}
            )
        return user_data
    if current is None:
        for field, message in (
            ("name", "A name is required to create the account."),
            ("phone", "A phone number is required to create the account."),
        ):
            if not user_data.get(field):
                raise ValidationError({field: [message]})
        return get_user_model().objects.create_user(**user_data)
    for field, value in user_data.items():
        setattr(current, field, value)
    current.save()
    return current


def _set_taxonomies(profile, subjects, levels):
    if subjects is not None:
        profile.subjects.set(subjects)
    if levels is not None:
        profile.levels.set(levels)
