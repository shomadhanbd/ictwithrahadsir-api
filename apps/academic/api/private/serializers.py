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
        read_only_fields = ["slug", "question_count", "subject_count"]


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
        read_only_fields = ["slug", "question_count"]


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
        read_only_fields = ["slug", "question_count", "chapter_count"]


class ChapterSerializer(serializers.ModelSerializer):
    subject_id = serializers.PrimaryKeyRelatedField(source="subject", queryset=Subject.objects.all())
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    def validate_subject_id(self, subject):
        # A question carries its subject as well as its chapter, so moving a
        # chapter that holds questions would leave them saying two things.
        # `question_blocks` is the question app's reverse relation, read by
        # name so this app does not import the one above it.
        if self.instance is not None and subject != self.instance.subject and self.instance.question_blocks.exists():
            raise serializers.ValidationError("This chapter has questions, so it cannot move to another subject.")
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
            "is_locked",
            "is_active",
        ]
        read_only_fields = ["slug", "question_count"]


class TopicSerializer(serializers.ModelSerializer):
    chapter_id = serializers.PrimaryKeyRelatedField(source="chapter", queryset=Chapter.objects.all())
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)

    def validate_chapter_id(self, chapter):
        # A question's topics must be of its chapter; see the chapter's rule.
        if self.instance is not None and chapter != self.instance.chapter and self.instance.question_blocks.exists():
            raise serializers.ValidationError("Questions are tagged with this topic, so it cannot move chapter.")
        return chapter

    class Meta:
        model = Topic
        fields = ["id", "name", "slug", "chapter_id", "chapter_name", "question_count", "is_active"]
        read_only_fields = ["slug", "question_count"]


class BatchSerializer(serializers.ModelSerializer):
    class_level_id = serializers.PrimaryKeyRelatedField(source="class_level", queryset=ClassLevel.objects.all())
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "name", "slug", "class_level_id", "class_level_name", "is_active", "order"]
        read_only_fields = ["slug"]
