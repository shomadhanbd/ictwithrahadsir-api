from django.db import models


class Role(models.TextChoices):
    """Role names, which double as `auth.Group` names. Listed by precedence."""

    ADMIN = "admin", "Admin"
    MODERATOR = "moderator", "Moderator"
    TEACHER = "teacher", "Teacher"
    STUDENT = "student", "Student"


#: Roles that reach the Django admin site. See `User.is_staff`.
BACK_OFFICE_ROLES = {Role.ADMIN, Role.MODERATOR}
