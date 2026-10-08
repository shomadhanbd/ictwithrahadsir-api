from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import OrderedModel, TimestampModel


class SmsMessage(TimestampModel):
    class Purpose(models.TextChoices):
        PHONE_VERIFY = "phone_verify", "Phone verification"
        PASSWORD_RESET = "password_reset", "Password reset"
        EXPIRY_REMINDER = "expiry_reminder", "Expiry reminder"
        ACCESS_ENDED = "access_ended", "Access ended notice"
        PURCHASE = "purchase", "Purchase / renewal notice"
        GUARDIAN = "guardian", "Message to a guardian"
        CUSTOM = "custom", "Custom message"

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    # Their body (an OTP code) is never stored.
    SECRET_PURPOSES = (Purpose.PHONE_VERIFY, Purpose.PASSWORD_RESET)

    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    phone = models.CharField(max_length=20)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.CharField(max_length=255, blank=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="sms_received"
    )
    # Empty when the system sent it.
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta(TimestampModel.Meta):
        verbose_name = "SMS message"
        verbose_name_plural = "SMS messages"
        indexes = [models.Index(fields=["purpose", "created_at"]), models.Index(fields=["phone"])]

    def __str__(self):
        return f"{self.get_purpose_display()} → {self.phone} ({self.status})"


class NoticeCategory(TimestampModel, OrderedModel):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_("slug"))

    class Meta:
        ordering = ["order", "title"]
        verbose_name_plural = "notice categories"

    def __str__(self):
        return self.title


class Notice(TimestampModel):
    """With no class levels or batches it is for everyone, visitors too."""

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_("slug"))
    body = models.TextField(blank=True)
    image = models.URLField(null=True, blank=True)
    categories = models.ManyToManyField(NoticeCategory, related_name="notices", blank=True)
    class_levels = models.ManyToManyField("academic.ClassLevel", related_name="notices", blank=True)
    batches = models.ManyToManyField("academic.Batch", related_name="notices", blank=True)

    def __str__(self):
        return self.title


class NoticeSeen(models.Model):
    """Notices newer than `seen_at` count as unread."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notice_seen")
    seen_at = models.DateTimeField()

    def __str__(self):
        return f"{self.user} saw notices at {self.seen_at}"
