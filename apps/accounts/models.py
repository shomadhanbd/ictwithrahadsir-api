import random
import string

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


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
    reset. Delivery goes through apps.core.sms so swapping in a real SMS
    gateway later needs no changes here."""

    phone = models.CharField(max_length=20, db_index=True)
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, phone: str) -> "OTP":
        length = settings.OTP_LENGTH
        code = "".join(random.choices(string.digits, k=length))
        otp = cls.objects.create(phone=phone, code=code)
        from apps.core.sms import get_sms_backend

        get_sms_backend().send(phone, f"Your ICT with Rahad Sir verification code is {code}")
        return otp

    @classmethod
    def verify(cls, phone: str, code: str) -> bool:
        cutoff = timezone.now() - timezone.timedelta(seconds=settings.OTP_TTL_SECONDS)
        otp = (
            cls.objects.filter(
                phone=phone, code=code, consumed_at__isnull=True, created_at__gte=cutoff
            )
            .order_by("-created_at")
            .first()
        )
        if not otp:
            return False
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["consumed_at"])
        return True
