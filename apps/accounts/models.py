import random
import string

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.core.services.factory import get_sms_backend


class UserManager(BaseUserManager):
    def create_user(self, phone=None, email=None, password=None, **extra_fields):
        if not phone and not email:
            raise ValueError("A user requires a phone number or an email address.")
        email = self.normalize_email(email) if email else None
        user = self.model(phone=phone, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("name", extra_fields.get("name") or "Admin")
        if not phone:
            phone = f"admin-{''.join(random.choices(string.digits, k=8))}"
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone=phone, email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        ADMIN = "admin", "Admin"

    name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    guardian_phone = models.CharField(max_length=20, null=True, blank=True)
    institution = models.CharField(max_length=255, null=True, blank=True)
    educational_session = models.CharField(max_length=100, null=True, blank=True)
    device_id = models.CharField(max_length=255, null=True, blank=True)
    fcm_token = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    image = models.URLField(null=True, blank=True)

    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["email", "name"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.name or self.phone or self.email or f"user-{self.pk}"

    @property
    def is_admin_panel_user(self):
        return self.is_staff or self.role in (self.Role.ADMIN, self.Role.INSTRUCTOR)


class OTP(models.Model):
    """One-time codes for phone verification (registration) and password
    reset. Delivery goes through apps.core.services.factory so swapping in a real SMS
    gateway later needs no changes here."""

    #: A wrong guess burns an attempt; the code is dead once they run out.
    #: Without this a 6-digit code is brute-forceable in seconds, which
    #: (since a verified OTP mints a full auth token) is account takeover.
    MAX_ATTEMPTS = 5

    phone = models.CharField(max_length=20, db_index=True)
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone", "-created_at"])]

    def __str__(self):
        return f"OTP for {self.phone}"

    @property
    def is_expired(self) -> bool:
        age = timezone.now() - self.created_at
        return age.total_seconds() > settings.OTP_TTL_SECONDS

    @property
    def is_usable(self) -> bool:
        return (
            self.consumed_at is None
            and self.attempts < self.MAX_ATTEMPTS
            and not self.is_expired
        )

    @classmethod
    def latest_for(cls, phone: str) -> "OTP | None":
        return cls.objects.filter(phone=phone).order_by("-created_at").first()

    @classmethod
    def seconds_until_resend(cls, phone: str) -> int:
        """Remaining cooldown before `phone` may request another code, or 0.

        `OTP_RESEND_COOLDOWN_SECONDS` has always been in settings but was
        never read, so nothing stopped an attacker from using the public
        get-otp endpoint to bombard a number with SMS at the platform's
        expense.
        """
        cooldown = getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)
        if not cooldown:
            return 0
        last = cls.latest_for(phone)
        if last is None:
            return 0
        elapsed = (timezone.now() - last.created_at).total_seconds()
        return max(0, int(cooldown - elapsed))

    @classmethod
    def issue(cls, phone: str) -> "OTP":
        code = "".join(random.choices(string.digits, k=settings.OTP_LENGTH))
        otp = cls.objects.create(phone=phone, code=code)
        get_sms_backend().send(phone, f"Your ICT with Rahad Sir verification code is {code}")
        return otp

    @classmethod
    def verify(cls, phone: str, code: str) -> bool:
        """Check `code` against the most recent code issued to `phone`.

        Deliberately keyed on the phone rather than on (phone, code): looking
        the row up by code meant a wrong guess matched nothing and so could
        not be counted, leaving the code brute-forceable.
        """
        otp = cls.latest_for(phone)
        if otp is None or not otp.is_usable:
            return False

        if not constant_time_compare(otp.code, str(code or "")):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return False

        otp.consumed_at = timezone.now()
        otp.save(update_fields=["consumed_at"])
        return True
