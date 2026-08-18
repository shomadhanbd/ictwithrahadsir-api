"""Manager and queryset for `User`.

`UserManager` used to sit at the top of `models.py`. It works there, but it
is the only manager in the project that did -- `billing` and `courses` keep
theirs in a `managers.py` -- and `models.py` is meant to describe the schema,
not how it is queried.

Splitting it also removes a forward reference: `create_superuser` needed
`User.Role.ADMIN` from a class defined *below* it in the same file. Here it
reaches the same choices through `self.model`, which is what a manager is
given for.
"""

import random
import string

from django.contrib.auth.base_user import BaseUserManager
from django.db import models


class UserQuerySet(models.QuerySet):
    """The role filters the admin screens and dashboard ask for repeatedly."""

    def students(self):
        return self.filter(role=self.model.Role.STUDENT)

    def instructors(self):
        return self.filter(role=self.model.Role.INSTRUCTOR)

    def admins(self):
        return self.filter(role=self.model.Role.ADMIN)

    def joined_since(self, when):
        return self.filter(date_joined__gte=when)


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    """Creates users, and carries `UserQuerySet`'s filters onto `User.objects`.

    `from_queryset` is what keeps both halves available: without it, adding a
    queryset method would mean it worked on `User.objects.all()` but not on
    `User.objects`, which is a confusing distinction to leave lying around.
    """

    def create_user(self, phone=None, email=None, password=None, **extra_fields):
        if not phone and not email:
            raise ValueError("A user requires a phone number or an email address.")
        email = self.normalize_email(email) if email else None
        user = self.model(phone=phone, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            # An account created by OTP alone has no password yet; an unusable
            # one lets `has_usable_password()` drive the client's
            # login-vs-register branching.
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("name", extra_fields.get("name") or "Admin")
        if not phone:
            # `phone` is the USERNAME_FIELD and is unique, so a superuser
            # created with only an email still needs one.
            phone = f"admin-{''.join(random.choices(string.digits, k=8))}"
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone=phone, email=email, password=password, **extra_fields)
