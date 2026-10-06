from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Group, PermissionsMixin
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import cached_property

from apps.core.text.phones import normalize_phone, validate_phone
from apps.identity.managers import OTPQuerySet, UserManager
from apps.identity.roles import BACK_OFFICE_ROLES, Role


class User(AbstractBaseUser, PermissionsMixin):
    Role = Role

    phone = models.CharField("Phone Number", max_length=20, unique=True, validators=[validate_phone])
    email = models.EmailField("Email Address", unique=True, null=True, blank=True)
    name = models.CharField("Full Name", max_length=150, blank=True)
    image = models.URLField("Profile Image", blank=True)

    fcm_token = models.CharField("FCM Token", max_length=255, blank=True)

    phone_verified_at = models.DateTimeField("Phone Verified At", null=True, blank=True)
    email_verified_at = models.DateTimeField("Email Verified At", null=True, blank=True)

    is_active = models.BooleanField("Active", default=True)
    date_joined = models.DateTimeField("Date Joined", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["-date_joined"])]

    def __str__(self):
        return self.name or self.phone

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone)
        self.email = self.email.lower() if self.email else None
        super().save(*args, **kwargs)

    @cached_property
    def role(self) -> str | None:
        """The primary role, from group membership. Prefetch `groups` on lists."""
        names = {group.name for group in self.groups.all()}
        return next((role for role in Role.values if role in names), None)

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    @transaction.atomic
    def set_role(self, role: str) -> None:
        """Make `role` the only role group; other groups are left alone."""
        self.groups.remove(*Group.objects.filter(name__in=Role.values))
        self.groups.add(Group.objects.get(name=role))
        self.__dict__.pop("role", None)

    @property
    def is_staff(self) -> bool:
        """Django admin access, derived so it cannot drift from the role."""
        return self.is_superuser or self.role in BACK_OFFICE_ROLES

    @property
    def can_sign_in(self) -> bool:
        # `has_usable_password()` reads an empty hash as usable, so check for one too.
        return bool(self.is_active and self.password and self.has_usable_password())


class OTP(models.Model):
    class Purpose(models.TextChoices):
        VERIFY = "verify", "Phone Verification"
        PASSWORD_RESET = "password_reset", "Password Reset"

    phone = models.CharField("Phone Number", max_length=20)
    code = models.CharField("Code", max_length=8)
    purpose = models.CharField("Purpose", max_length=20, choices=Purpose.choices, default=Purpose.VERIFY)
    created_at = models.DateTimeField("Issued At", auto_now_add=True)
    consumed_at = models.DateTimeField("Consumed At", null=True, blank=True)
    attempts = models.PositiveSmallIntegerField("Failed Attempts", default=0)
    meta = models.JSONField("Request Meta", default=dict, blank=True)  # debugging only

    objects = OTPQuerySet.as_manager()

    class Meta:
        verbose_name = "One-time Code"
        verbose_name_plural = "One-time Codes"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone", "purpose", "-created_at"])]

    def __str__(self):
        return f"OTP for {self.phone}"

    @property
    def is_usable(self) -> bool:
        age = (timezone.now() - self.created_at).total_seconds()
        return (
            self.consumed_at is None and self.attempts < settings.OTP_MAX_ATTEMPTS and age <= settings.OTP_TTL_SECONDS
        )
