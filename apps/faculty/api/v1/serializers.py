from rest_framework import serializers

from apps.core.api.fields import MediaField
from apps.faculty.models import Teacher


class TeacherSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to='team', required=False)

    class Meta:
        model = Teacher
        fields = ['id', 'name', 'designation', 'description', 'type', 'order', 'image']
