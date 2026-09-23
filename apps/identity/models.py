import string

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Group, PermissionsMixin
from django.db import models, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, get_random_string
from django.utils.functional import cached_property

from apps.core.phones import normalize_phone, validate_phone
from apps.identity.managers import UserManager
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
    def is_phone_verified(self) -> bool:
        return self.phone_verified_at is not None


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
    #: Debugging only, e.g. {"platform": "android"}. Never filtered on.
    meta = models.JSONField("Request Meta", default=dict, blank=True)

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

    @classmethod
    def issue(cls, phone: str, purpose: str, meta: dict | None = None) -> "OTP":
        return cls.objects.create(
            phone=phone,
            code=get_random_string(settings.OTP_LENGTH, allowed_chars=string.digits),
            purpose=purpose,
            meta=meta or {},
        )

    @classmethod
    def verify(cls, phone: str, code: str, purpose: str) -> bool:
        otp = cls.latest_for(phone, purpose)
        if otp is None or not otp.is_usable:
            return False

        if not constant_time_compare(otp.code, str(code or "")):
            cls.objects.filter(pk=otp.pk).update(attempts=models.F("attempts") + 1)
            return False

        # Conditional, so two concurrent verifies cannot both succeed.
        spent = cls.objects.filter(pk=otp.pk, consumed_at__isnull=True).update(consumed_at=timezone.now())
        return bool(spent)

    @classmethod
    def latest_for(cls, phone: str, purpose: str) -> "OTP | None":
        return cls.objects.filter(phone=phone, purpose=purpose).order_by("-created_at").first()

    @classmethod
    def seconds_until_resend(cls, phone: str) -> int:
        """0 if a send is allowed now, otherwise how long to wait."""
        now = timezone.now()
        recent = cls.objects.filter(phone=phone, created_at__gte=now - timezone.timedelta(hours=1))
        recent = recent.order_by("created_at")

        waits = [0]
        newest = recent.last()
        if newest and settings.OTP_RESEND_COOLDOWN_SECONDS:
            elapsed = (now - newest.created_at).total_seconds()
            waits.append(int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed))

        cap = settings.OTP_RATE_LIMIT_PER_PHONE_PER_HOUR
        if cap and recent.count() >= cap:
            waits.append(int(3600 - (now - recent.first().created_at).total_seconds()))

        return max(waits)
