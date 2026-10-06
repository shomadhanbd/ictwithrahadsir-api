from django.db import models


class Role(models.TextChoices):
    """Role names, which double as `auth.Group` names. Listed by precedence."""

    ADMIN = "admin", "Admin"
    MODERATOR = "moderator", "Moderator"
    TEACHER = "teacher", "Teacher"
    STUDENT = "student", "Student"


BACK_OFFICE_ROLES = {Role.ADMIN, Role.MODERATOR}
TEACHER_CREATABLE_ROLES = {Role.STUDENT}
MODERATOR_APP_LABELS = ("content",)


def has_any_role(user, *roles) -> bool:
    # Not `is_staff`: that is also true for moderators.
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_superuser or user.role in roles)


def is_full_admin(user) -> bool:
    return has_any_role(user, Role.ADMIN)


def is_content_staff(user) -> bool:
    return has_any_role(user, Role.ADMIN, Role.MODERATOR)


def is_teaching_staff(user) -> bool:
    return has_any_role(user, Role.ADMIN, Role.TEACHER)
