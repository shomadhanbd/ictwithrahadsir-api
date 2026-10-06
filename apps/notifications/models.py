from django.conf import settings
from django.db import models

from apps.core.models import TimestampModel


class SmsMessage(TimestampModel):
    """One SMS the platform sent or tried to send. `sent_by` is empty when the system sent it."""

    class Purpose(models.TextChoices):
        PHONE_VERIFY = "phone_verify", "Phone verification"
        PASSWORD_RESET = "password_reset", "Password reset"
        EXPIRY_REMINDER = "expiry_reminder", "Expiry reminder"
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
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta(TimestampModel.Meta):
        verbose_name = "SMS message"
        verbose_name_plural = "SMS messages"
        indexes = [models.Index(fields=["purpose", "created_at"]), models.Index(fields=["phone"])]

    def __str__(self):
        return f"{self.get_purpose_display()} → {self.phone} ({self.status})"
