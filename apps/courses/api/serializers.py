from rest_framework import serializers

from apps.core.api.serializers.fields import MediaField
from apps.courses.models import Course, CourseMaterial, Routine
from apps.courses.validators import validate_section_in_course


class CourseOwnedSerializer(serializers.ModelSerializer):
    """A row inside one course; a section it names must belong to that course."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        validate_section_in_course(
            attrs.get("section", getattr(self.instance, "section", None)),
            attrs.get("course", getattr(self.instance, "course", None)),
        )
        return attrs


class RoutineSerializer(CourseOwnedSerializer):
    link = MediaField(required=False)
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())

    class Meta:
        model = Routine
        fields = ["id", "course_id", "title", "link"]
        read_only_fields = ["id"]


class CourseMaterialSerializer(CourseOwnedSerializer):
    file = MediaField(required=False)
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CourseMaterial
        fields = ["id", "title", "type", "course_id", "file", "created_at"]
        read_only_fields = ["id", "created_at"]
