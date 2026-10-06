from rest_framework import serializers

from apps.academic.models import ClassLevel, Group
from apps.core.api.serializers.fields import PhoneField
from apps.profiles.models import StudentProfile
from apps.profiles.validators import clean_student_audience


class StudentProfileSerializer(serializers.ModelSerializer):
    """The nested `student` block on every user payload, with the guardian flattened in."""

    GUARDIAN_FIELDS = ("guardian_name", "guardian_phone")

    guardian_name = serializers.CharField(source="guardian.name", required=False, allow_blank=True, default="")
    guardian_phone = PhoneField(source="guardian.phone", required=False, allow_blank=True, default="")
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # A missing guardian row reads as None, not the field default.
        for field in self.GUARDIAN_FIELDS:
            if data.get(field) is None:
                data[field] = ""
        return data


class AdminStudentProfileSerializer(StudentProfileSerializer):
    """Retired classes and groups stay assignable from the admin panel."""

    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all(), required=False, allow_null=True
    )
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.all(), required=False, allow_null=True
    )
