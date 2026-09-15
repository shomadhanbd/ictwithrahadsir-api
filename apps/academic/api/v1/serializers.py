"""Slugs are read-only throughout: every model builds its own on save."""

from rest_framework import serializers

from apps.academic.models import Batch, ClassLevel, Group, Subject


class SubjectSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all()
    )
    group_id = serializers.PrimaryKeyRelatedField(source="group", queryset=Group.objects.all())
    #: So a table renders from one request instead of joining three client-side.
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "slug",
            "class_level_id",
            "class_level_name",
            "group_id",
            "group_name",
            "question_count",
            "chapter_count",
            "is_active",
            "order",
        ]
        read_only_fields = ["slug"]


class ClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = [
            "id",
            "name",
            "slug",
            "group_count",
            "subject_count",
            "question_count",
            "chapter_count",
            "is_active",
            "order",
        ]
        read_only_fields = ["slug"]


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "slug",
            "subject_count",
            "question_count",
            "chapter_count",
            "is_active",
            "order",
        ]
        read_only_fields = ["slug"]


class BatchSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all()
    )
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "name", "slug", "class_level_id", "class_level_name", "is_active", "order"]
        read_only_fields = ["slug"]
