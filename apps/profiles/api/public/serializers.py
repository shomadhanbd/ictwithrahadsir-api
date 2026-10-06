from rest_framework import serializers

from apps.core.api.serializers.fields import MediaField
from apps.profiles.models import TeacherProfile


class TeacherSerializer(serializers.ModelSerializer):
    """The public roster entry; its keys are frozen by `test_response_shapes.PUBLIC_TEACHER_KEYS`."""

    name = serializers.CharField(source="user.name", read_only=True)
    image = MediaField(source="user.image", read_only=True)

    class Meta:
        model = TeacherProfile
        fields = ["id", "name", "designation", "description", "type", "order", "image"]
