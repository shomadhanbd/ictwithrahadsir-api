"""Slugs are read-only throughout: typed in the Django admin, or built from the
name on save when left blank.

The `*_name` fields spare the panel a second request to resolve a foreign key;
the matching views `select_related` so they cost no extra query.
"""

from rest_framework import serializers

from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic


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


class SubjectSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(source="class_level", queryset=ClassLevel.objects.all())
    group_id = serializers.PrimaryKeyRelatedField(source="group", queryset=Group.objects.all())
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


class ChapterSerializer(serializers.ModelSerializer):
    subject_id = serializers.PrimaryKeyRelatedField(source="subject", queryset=Subject.objects.all())
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id",
            "name",
            "slug",
            "subject_id",
            "subject_name",
            "chapter_number",
            "question_count",
            "is_locked",
            "is_active",
        ]
        read_only_fields = ["slug"]


class TopicSerializer(serializers.ModelSerializer):
    chapter_id = serializers.PrimaryKeyRelatedField(source="chapter", queryset=Chapter.objects.all())
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)

    class Meta:
        model = Topic
        fields = ["id", "name", "slug", "chapter_id", "chapter_name", "is_active"]
        read_only_fields = ["slug"]


class BatchSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(source="class_level", queryset=ClassLevel.objects.all())
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "name", "slug", "class_level_id", "class_level_name", "is_active", "order"]
        read_only_fields = ["slug"]
