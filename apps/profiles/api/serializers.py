from rest_framework import serializers

from apps.academic.models import ClassLevel, Group
from apps.core.api.serializers.fields import PhoneField
from apps.profiles.models import StudentProfile
from apps.profiles.validators import clean_student_audience


class StudentProfileSerializer(serializers.ModelSerializer):
    """The nested `student` block on every user payload."""

    guardian_phone = PhoneField(required=False, allow_blank=True)
    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.active(), required=False, allow_null=True
    )
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.active(), required=False, allow_null=True
    )

    class Meta:
        model = StudentProfile
        fields = [
            "guardian_name",
            "guardian_phone",
            "institution",
            "educational_session",
            "address",
            "class_level_id",
            "group_id",
        ]

    def validate(self, attrs):
        return clean_student_audience(super().validate(attrs), self._saved_profile())

    def _saved_profile(self):
        """The profile being edited. Nested in a user payload, it hangs off the parent's user, so a write of
        just `group_id` is checked against the class already saved rather than against none."""
        if self.instance is not None:
            return self.instance
        user = getattr(self.parent, "instance", None)
        return getattr(user, "student", None) if user is not None else None


class AdminStudentProfileSerializer(StudentProfileSerializer):
    """Retired classes and groups stay assignable from the admin panel."""

    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all(), required=False, allow_null=True
    )
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.all(), required=False, allow_null=True
    )
