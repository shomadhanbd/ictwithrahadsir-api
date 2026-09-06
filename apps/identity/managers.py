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

from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.utils import timezone

from apps.identity.phones import normalize_phone


class UserQuerySet(models.QuerySet):
    """The filters the admin screens and dashboard ask for repeatedly."""

    def registered(self):
        """Accounts whose owner actually finished signing up.

        Excludes the placeholder rows `/auth/otp/verify/` has to create -- see
        `User.registered_at` for why they exist.
        """
        return self.filter(registered_at__isnull=False)

    def students(self):
        """Real students: role `student`, sign-up finished.

        The `registered()` half is folded in here rather than left to each
        caller because forgetting it is silent -- the count is simply wrong,
        by however many people abandoned registration that month.
        """
        return self.filter(role=self.model.Role.STUDENT).registered()

    def joined_since(self, when):
        return self.filter(date_joined__gte=when)


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    """Creates users, and carries `UserQuerySet`'s filters onto `User.objects`.

    `from_queryset` is what keeps both halves available: without it, adding a
    queryset method would mean it worked on `User.objects.all()` but not on
    `User.objects`, which is a confusing distinction to leave lying around.
    """

    def create_user(self, phone=None, email=None, password=None, **extra_fields):
        """Create a real account -- somebody deliberately put this person here.

        `registered_at` is stamped by default for exactly that reason. The one
        caller that must *not* stamp it is `create_unverified` below.
        """
        if not phone and not email:
            raise ValueError("A user requires a phone number or an email address.")
        extra_fields.setdefault("registered_at", timezone.now())
        # Both identifiers are normalised in one place, for the same reason:
        # the seed command, the shell and a spreadsheet import do not go
        # through a serializer, and a second spelling of a number is a second
        # account.
        phone = normalize_phone(phone)
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
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone=phone, email=email, password=password, **extra_fields)

    def create_unverified(self, phone):
        """A placeholder for a phone that has passed OTP but has no profile.

        `/auth/otp/verify/` returns a token, and the web client stores it as
        the session cookie before the user has filled anything in -- so a row
        has to exist to own that token. Leaving `registered_at` null is what
        keeps the half-finished ones out of the roster and the student count
        until `/auth/register/` completes them.
        """
        return self.create_user(
            phone=phone, role=self.model.Role.STUDENT, registered_at=None
        )
