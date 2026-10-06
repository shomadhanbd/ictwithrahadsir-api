"""Who a person is, separately from how they sign in; identity depends on profiles, never back."""

from django.conf import settings
from django.db import models

from apps.core.text.phones import normalize_phone, validate_phone
from apps.profiles.managers import TeacherProfileQuerySet


class TeacherProfile(models.Model):
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
    order = models.PositiveIntegerField("Order", default=0)

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

    class Meta:
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"

    def __str__(self):
        return f"Student: {self.user}"


class GuardianProfile(models.Model):
    """The student's guardian (not a login); every student has one, blank if unknown."""

    student = models.OneToOneField(StudentProfile, on_delete=models.CASCADE, related_name="guardian")
    name = models.CharField("Guardian's Name", max_length=150, blank=True)
    phone = models.CharField("Guardian's Phone Number", max_length=20, blank=True, validators=[validate_phone])
    relation = models.CharField("Relation", max_length=50, blank=True)
    occupation = models.CharField("Occupation", max_length=150, blank=True)

    class Meta:
        verbose_name = "Guardian"
        verbose_name_plural = "Guardians"

    def __str__(self):
        return self.name or f"Guardian of {self.student.user}"

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone) or ""
        super().save(*args, **kwargs)
