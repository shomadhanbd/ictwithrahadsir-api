from django.db import models


class Role(models.TextChoices):
    """Role names, which double as `auth.Group` names. Listed by precedence."""

    ADMIN = "admin", "Admin"
    MODERATOR = "moderator", "Moderator"
    TEACHER = "teacher", "Teacher"
    STUDENT = "student", "Student"


# What each role may do

BACK_OFFICE_ROLES = {Role.ADMIN, Role.MODERATOR}  # may use the Django admin
MODERATOR_APP_LABELS = ("content",)  # the apps a moderator manages there
TEACHER_CREATABLE_ROLES = {Role.STUDENT}  # the accounts a teacher may create


# Permission checks; a superuser passes every one


def is_full_admin(user) -> bool:
    return _has_any_role(user, Role.ADMIN)


def is_content_staff(user) -> bool:
    return _has_any_role(user, Role.ADMIN, Role.MODERATOR)


def is_teaching_staff(user) -> bool:
    return _has_any_role(user, Role.ADMIN, Role.TEACHER)


def _has_any_role(user, *roles) -> bool:
    # Checks the role, not `is_staff`: that is also true for moderators.
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_superuser or user.role in roles)


# Accounts

SUPERUSER_ACCOUNT_MESSAGE = "Only a superuser may change a superuser's account."


def may_change_account(actor, account) -> bool:
    """A superuser's account is changed only by a superuser: anyone else could set its phone, then reset its
    password by OTP. Every path that writes an account (user API, teachers API, Django admin) asks this."""
    return account is None or not account.is_superuser or bool(getattr(actor, "is_superuser", False))
