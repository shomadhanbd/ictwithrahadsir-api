"""Inbound help requests from students and visitors.

A helpdesk inbox, not content: these arrive from the public contact
form, get read and replied to by staff, and are never edited as pages.
They sat in `cms` only because that app had become a catch-all.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimestampModel


class ContactMessage(TimestampModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
    )
    name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    reply_message = models.TextField(blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_replies",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.subject}"

    @property
    def reply(self):
        return self.reply_message
