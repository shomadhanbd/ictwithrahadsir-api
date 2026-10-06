from django.contrib.auth import get_user_model
from django.db import transaction

from apps.core import providers
from apps.profiles.models import StudentProfile, TeacherProfile

TEACHER_ROLE = "teacher"


def ensure_teacher_role(profile) -> None:
    """Give a teacher's account the `teacher` role, unless an admin or moderator would be demoted."""
    if not profile.user.has_role("admin", "moderator"):
        profile.user.set_role(TEACHER_ROLE)


def release_teacher_account(user) -> None:
    """An account that is no longer a teacher's: its course assignments end and it loses the teacher role.
    An admin's or moderator's own role is left alone."""
    end_teaching = providers.get("profiles.end_teaching")  # courses sits above this app
    if end_teaching is not None:
        end_teaching(user)
    user.groups.remove(*user.groups.filter(name=TEACHER_ROLE))
    user.__dict__.pop("role", None)  # `role` is cached on the instance; recompute it without the teacher group


def save_student_profile(user, data) -> None:
    """Writes the nested `student` block of a user payload."""
    if data is None:
        return
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    user.student = profile  # replaces a stale `select_related` copy


def ensure_student_profile(user, *, institution=None, educational_session=None, class_level=None, group=None):
    """A student profile, filled with whatever sign-up gave."""
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    if institution is not None:
        profile.institution = institution
    if educational_session is not None:
        profile.educational_session = educational_session
    if class_level is not None:
        profile.class_level = class_level
        profile.group = group
    profile.save()
    return profile


@transaction.atomic
def create_teacher(data) -> TeacherProfile:
    """A teacher with an account of their own, created together."""
    data = dict(data)
    account = data.pop("user", None) or {}
    user = get_user_model().objects.create_user(**account, role=TEACHER_ROLE)
    subjects, levels = data.pop("subjects", None), data.pop("levels", None)
    profile = TeacherProfile.objects.create(user=user, **data)
    _set_taxonomies(profile, subjects, levels)
    return profile


@transaction.atomic
def update_teacher(profile, data) -> TeacherProfile:
    """Edits the teacher and their account together."""
    data = dict(data)
    account = data.pop("user", None)
    if account:
        for field, value in account.items():
            setattr(profile.user, field, value)
        profile.user.save()
    subjects, levels = data.pop("subjects", None), data.pop("levels", None)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    _set_taxonomies(profile, subjects, levels)
    return profile


@transaction.atomic
def delete_teacher(profile) -> None:
    release_teacher_account(profile.user)
    profile.delete()


def _set_taxonomies(profile, subjects, levels):
    if subjects is not None:
        profile.subjects.set(subjects)
    if levels is not None:
        profile.levels.set(levels)
