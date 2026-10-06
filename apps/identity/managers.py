from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.db.models import Q

from apps.core.text.phones import normalize_phone
from apps.identity.roles import Role


class UserQuerySet(models.QuerySet):
    def registered(self):
        """Everything but abandoned sign-ups, which are the only accounts without a name."""
        return self.exclude(name="")

    def students(self):
        return self.filter(groups__name=Role.STUDENT).registered()

    def joined_since(self, when):
        return self.filter(date_joined__gte=when)

    def search(self, term):
        return self.filter(Q(name__icontains=term) | Q(phone__icontains=term) | Q(email__icontains=term))


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    def create_user(self, phone=None, password=None, role=None, **extra):
        phone = normalize_phone(phone)
        if not phone:
            raise ValueError("A valid phone number is required")

        extra.pop("is_staff", None)  # derived from the role
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
        """A bare row mid-OTP; `registered()` excludes it until a name is set."""
        return self.create_user(phone=phone, password=None)


class OTPQuerySet(models.QuerySet):
    def latest_for(self, phone, purpose):
        return self.filter(phone=phone, purpose=purpose).order_by("-created_at").first()

    def older_than(self, when):
        return self.filter(created_at__lt=when)
