import random
import string

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.identity.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        """What this person does at the coaching centre.

        `INSTRUCTOR` is the teacher role. The stored value stays
        `"instructor"` because it is already in the database, in both
        frontends' role dropdowns, and in the OpenAPI schema -- renaming the
        value would be a migration and a frontend change to gain a synonym.

        `MODERATOR` is the tier that was missing. Somebody has to post
        notices, publish the homepage banners and answer the contact inbox,
        and that person is not a teacher. Without a role for them they were
        made an `instructor`, which handed a content-desk job a teaching
        token -- and, before the permission split, the payments screen too.

        The tiers these map to live in `apps.core.api.permissions`. Roles say
        who somebody is; permissions say what that lets them touch.
        """

        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        MODERATOR = "moderator", "Moderator"
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

    #: When sign-up was completed. Null means this row is a placeholder:
    #: `/auth/otp/verify/` has to create a user before `/auth/register/` runs,
    #: because the client stores the token it hands back as its session. Every
    #: abandoned registration therefore left a permanent nameless "student" in
    #: the roster and in the dashboard's student count. `UserQuerySet.students`
    #: filters on this; see `UserManager.create_unverified`.
    registered_at = models.DateTimeField(null=True, blank=True)

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


class OTP(models.Model):
    """One-time codes for phone verification (registration) and password
    reset. Delivery goes through apps.core.services.factory so swapping in a real SMS
    gateway later needs no changes here."""

    #: A wrong guess burns an attempt; the code is dead once they run out.
    #: Without this a 6-digit code is brute-forceable in seconds, which
    #: (since a verified OTP mints a full auth token) is account takeover.
    MAX_ATTEMPTS = 5

    phone = models.CharField(max_length=20)
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        # Serves the `phone=` lookups too -- `phone` is the leading column --
        # so the field carries no `db_index` of its own.
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
        """Create a code for `phone`. Does not send it.

        Delivery lives in `apps.identity.services.send_otp`, so creating a
        row is not by itself a call out to an SMS gateway -- a model save
        that reaches the network cannot be used from a fixture, a migration
        or a test without stubbing the gateway out.
        """
        code = "".join(random.choices(string.digits, k=settings.OTP_LENGTH))
        return cls.objects.create(phone=phone, code=code)

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
