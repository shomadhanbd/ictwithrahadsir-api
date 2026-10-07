from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.db.models import Q

from apps.core.text.phones import normalize_phone
from apps.identity.roles import Role


class UserQuerySet(models.QuerySet):
    def students(self):
        return self.filter(groups__name=Role.STUDENT)

    def joined_since(self, since):
        return self.filter(date_joined__gte=since)

    def search(self, term):
        """Name, phone or email containing `term`."""
        return self.filter(Q(name__icontains=term) | Q(phone__icontains=term) | Q(email__icontains=term))


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    def create_user(self, phone=None, password=None, role=None, **fields):
        phone = normalize_phone(phone)
        if not phone:
            raise ValueError("A valid phone number is required")

        fields.pop("is_staff", None)  # a property derived from the role, so it cannot be set
        user = self.model(phone=phone, **fields)
        user.set_password(password)
        user.save(using=self._db)
        user.set_role(role or Role.STUDENT)
        return user

    def create_superuser(self, phone=None, password=None, **fields):
        fields["is_superuser"] = True
        fields.setdefault("name", "Admin")
        return self.create_user(phone, password, role=Role.ADMIN, **fields)

    def create_unverified(self, phone):
        """A bare row mid-OTP; registering fills in the name and password."""
        return self.create_user(phone=phone, password=None)


class OTPQuerySet(models.QuerySet):
    def latest_for(self, phone, purpose):
        return self.filter(phone=phone, purpose=purpose).order_by("-created_at").first()
