from django.contrib.auth.base_user import BaseUserManager
from django.db import models

from apps.core.phones import normalize_phone
from apps.identity.roles import Role


class UserQuerySet(models.QuerySet):
    def registered(self):
        """Everything but abandoned sign-ups.

        A name is the one thing every deliberate creation path sets and
        `create_unverified` does not. Not "has a password": admin-created and
        imported accounts have none and still belong on the roster.
        """
        return self.exclude(name="")

    def students(self):
        return self.filter(groups__name=Role.STUDENT).registered()

    def joined_since(self, when):
        return self.filter(date_joined__gte=when)


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    def create_user(self, phone=None, password=None, role=None, **extra):
        """Roles are group memberships, so they are attached after the save."""
        phone = normalize_phone(phone)
        if not phone:
            raise ValueError("A valid phone number is required")

        extra.pop("is_staff", None)  # a property now, but callers still pass it
        user = self.model(phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        user.set_role(role or Role.STUDENT)
        return user

    def create_superuser(self, phone=None, password=None, **extra):
        extra["is_superuser"] = True
        extra.setdefault("name", "Admin")
        return self.create_user(phone, password, role=Role.ADMIN, **extra)

    def create_unverified(self, phone):
        """A bare row mid-OTP. `registered()` excludes it until name is set."""
        return self.create_user(phone=phone, password=None)
