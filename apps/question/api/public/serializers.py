from rest_framework import serializers

from apps.question.models import QuestionOption


class PracticeQueryParamsSerializer(serializers.Serializer):
    chapter = serializers.IntegerField(min_value=1)
    topic = serializers.IntegerField(min_value=1, required=False)
    count = serializers.IntegerField(min_value=1, required=False)


class OptionSerializer(serializers.ModelSerializer):
    """What a student may see of an option: no answer key."""

    class Meta:
        model = QuestionOption
        fields = ["id", "label", "content", "position"]


class PracticeChapterSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="chapter.pk")
    name = serializers.CharField(source="chapter.name")
    number = serializers.IntegerField(source="chapter.chapter_number")
    question_count = serializers.IntegerField()


class PracticeSubjectSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="subject.pk")
    name = serializers.CharField(source="subject.name")
    chapters = PracticeChapterSerializer(many=True)


class PracticeLevelSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="level.pk")
    name = serializers.CharField(source="level.name")
    subjects = PracticeSubjectSerializer(many=True)


class PracticeQuestionSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    prompt_content = serializers.CharField()
    select_mode = serializers.CharField()
    stimulus = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    correct_option_ids = serializers.SerializerMethodField()
    explanation = serializers.CharField()

    def _options(self, question):
        return sorted(question.options.all(), key=lambda o: (o.position, o.pk))

    def get_stimulus(self, question) -> dict | None:
        if not question.question_set_id:
            return None
        return {"type": question.question_set.stimulus_type, "content": question.question_set.stimulus_content}

    def get_options(self, question) -> list[dict]:
        return [{"id": o.pk, "label": o.label, "content": o.content} for o in self._options(question)]

    def get_correct_option_ids(self, question) -> list[int]:
        return [o.pk for o in self._options(question) if o.is_correct]
