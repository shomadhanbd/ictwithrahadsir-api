from rest_framework import serializers

from apps.core.api.fields import MediaField
from apps.courses.models import Course
from apps.faculty.models import CourseInstructor, Teacher
from apps.identity.models import User


class TeacherSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to='team', required=False)

    class Meta:
        model = Teacher
        fields = ['id', 'name', 'designation', 'description', 'type', 'order', 'image']


class InstructorSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="instructor", required=False)
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=User.objects.all(), required=False, allow_null=True
    )
    # Optional: link the assignment to a roster teacher. When absent, one is
    # created from the flat fields below, so the admin panel's existing
    # payload keeps working unchanged.
    teacher_id = serializers.PrimaryKeyRelatedField(
        source="teacher", queryset=Teacher.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CourseInstructor
        fields = [
            "id",
            "course_id",
            "user_id",
            "name",
            "email",
            "phone",
            "designation",
            "description",
            "institute",
            "type",
            "order",
            "commission",
            "image",
            "teacher_id",
        ]
        read_only_fields = ["id"]

    def _ensure_teacher(self, validated_data):
        """Every assignment should point at a roster teacher.

        The admin form already has a teacher picker -- it just copies the
        name into the flat fields rather than sending an id. Until it sends
        one, create the roster entry from what it does send, so the link
        exists either way. Never matched by name: two real people can share
        one.
        """
        if validated_data.get("teacher"):
            return
        validated_data["teacher"] = Teacher.objects.create(
            name=validated_data.get("name", ""),
            designation=validated_data.get("designation", ""),
            description=validated_data.get("description", ""),
            type=validated_data.get("type", Teacher.Type.INSTRUCTOR),
            image=validated_data.get("image"),
        )

    def create(self, validated_data):
        self._ensure_teacher(validated_data)
        return super().create(validated_data)


class PublicInstructorSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = CourseInstructor
        fields = ["id", "name", "designation", "description", "type", "order", "image"]
