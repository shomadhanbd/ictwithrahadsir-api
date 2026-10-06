from rest_framework import serializers

from apps.academic.models import Batch, ClassLevel, Group


class PublicClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = ["id", "name", "slug"]


class PublicGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name", "slug"]


class PublicBatchSerializer(serializers.ModelSerializer):
    class_level = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "name", "slug", "class_level"]
