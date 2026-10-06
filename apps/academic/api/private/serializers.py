from rest_framework import serializers

from apps.academic import services
from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic
from apps.academic.validators import validate_chapter_subject_change, validate_topic_chapter_change
from apps.core.api.fields import LiveCount


class ClassLevelSerializer(serializers.ModelSerializer):
    group_count = LiveCount()
    subject_count = LiveCount()
    chapter_count = LiveCount()

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
        read_only_fields = ["slug", "question_count"]


class GroupSerializer(serializers.ModelSerializer):
    subject_count = LiveCount()
    chapter_count = LiveCount()

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
        read_only_fields = ["slug", "question_count"]


class SubjectSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(source="class_level", queryset=ClassLevel.objects.all())
    group_id = serializers.PrimaryKeyRelatedField(source="group", queryset=Group.objects.all())
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)
    chapter_count = LiveCount()

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
        read_only_fields = ["slug", "question_count"]


class ChapterSerializer(serializers.ModelSerializer):
    subject_id = serializers.PrimaryKeyRelatedField(source="subject", queryset=Subject.objects.all())
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    def validate_subject_id(self, subject):
        validate_chapter_subject_change(self.instance, subject)
        return subject

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
            "practice_enabled",
            "is_active",
        ]
        read_only_fields = ["slug", "question_count"]


class TopicSerializer(serializers.ModelSerializer):
    chapter_id = serializers.PrimaryKeyRelatedField(source="chapter", queryset=Chapter.objects.all())
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)

    def validate_chapter_id(self, chapter):
        validate_topic_chapter_change(self.instance, chapter)
        return chapter

    class Meta:
        model = Topic
        fields = ["id", "name", "slug", "chapter_id", "chapter_name", "question_count", "is_active", "order"]
        read_only_fields = ["slug", "question_count"]

    def create(self, validated_data):
        return services.create_topic(**validated_data)


class BatchSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(source="class_level", queryset=ClassLevel.objects.all())
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "name", "slug", "class_level_id", "class_level_name", "is_active", "order"]
        read_only_fields = ["slug"]
