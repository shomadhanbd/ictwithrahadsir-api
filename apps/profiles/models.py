"""Who a person is, separately from how they sign in; identity depends on profiles, never back."""

from django.conf import settings
from django.db import models

from apps.core.models import OrderedModel
from apps.core.text.phones import normalize_phone, validate_phone
from apps.profiles.managers import TeacherProfileQuerySet


class TeacherProfile(OrderedModel):
    """Teacher-only fields; name, phone and photo live on the `User`."""

    class Type(models.TextChoices):
        PERMANENT = "permanent", "Permanent Teacher"
        GUEST = "guest", "Guest Teacher"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher")
    designation = models.CharField("Designation", max_length=150, blank=True)
    description = models.TextField("Bio", blank=True)
    experience = models.CharField("Experience", max_length=255, blank=True)
    institute = models.CharField("Institution", max_length=255, blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.PERMANENT)
    subjects = models.ManyToManyField("academic.Subject", related_name="teachers", blank=True)
    levels = models.ManyToManyField("academic.ClassLevel", related_name="teachers", blank=True)

    objects = TeacherProfileQuerySet.as_manager()

    class Meta:
        verbose_name = "Teacher Profile"
        verbose_name_plural = "Teacher Profiles"
        ordering = ["order", "pk"]

    def __str__(self):
        return f"Teacher: {self.user}"


class StudentProfile(models.Model):
    """Student-only fields."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student")
    class_level = models.ForeignKey(
        "academic.ClassLevel", null=True, blank=True, on_delete=models.SET_NULL, related_name="students"
    )
    group = models.ForeignKey(
        "academic.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="students"
    )
    institution = models.CharField("Institution", max_length=255, blank=True)
    educational_session = models.CharField("Educational Session", max_length=100, blank=True)
    address = models.TextField("Address", blank=True)
    guardian_name = models.CharField("Guardian's Name", max_length=150, blank=True)
    guardian_phone = models.CharField("Guardian's Phone Number", max_length=20, blank=True, validators=[validate_phone])

    class Meta:
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"

    def __str__(self):
        return f"Student: {self.user}"

    def save(self, *args, **kwargs):
        self.guardian_phone = normalize_phone(self.guardian_phone) or ""
        super().save(*args, **kwargs)
