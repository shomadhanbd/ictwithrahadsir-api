from rest_framework import serializers

from apps.core.api.serializers.fields import MediaField
from apps.courses.models import Course
from apps.feedback.models import Feedback
from apps.feedback.validators import validate_feedback

COMMENT_MAX_LENGTH = 2000


class FeedbackCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["slug", "title"]


class FeedbackSerializer(serializers.ModelSerializer):
    course = FeedbackCourseSerializer(read_only=True)
    image = MediaField(bare=True)

    class Meta:
        model = Feedback
        fields = ["id", "source", "course", "name", "designation", "image", "rating", "comment", "created_at"]
        read_only_fields = fields


class HomeTestimonialSerializer(serializers.ModelSerializer):
    """The `/home` shape the website already reads."""

    description = serializers.CharField(source="comment")
    ratings = serializers.IntegerField(source="rating")
    image = MediaField()

    class Meta:
        model = Feedback
        fields = ["id", "name", "designation", "description", "ratings", "image"]
        read_only_fields = fields


class CourseRatingQuerySerializer(serializers.Serializer):
    course = serializers.SlugRelatedField(slug_field="slug", queryset=Course.objects.available())


class FeedbackRequestSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=COMMENT_MAX_LENGTH, trim_whitespace=True)


class MyFeedbackSerializer(serializers.ModelSerializer):
    course = FeedbackCourseSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display")

    class Meta:
        model = Feedback
        fields = ["id", "source", "course", "rating", "comment", "status", "status_label", "created_at", "updated_at"]
        read_only_fields = fields


class AdminFeedbackSerializer(serializers.ModelSerializer):
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)
    author = serializers.SerializerMethodField()
    image = MediaField(bare=True, null_as="")
    comment = serializers.CharField(max_length=COMMENT_MAX_LENGTH)
    # Staff add feedback they already trust.
    status = serializers.ChoiceField(choices=Feedback.Status.choices, default=Feedback.Status.APPROVED)

    class Meta:
        model = Feedback
        fields = [
            "id",
            "source",
            "course_id",
            "course_title",
            "author",
            "name",
            "designation",
            "image",
            "rating",
            "comment",
            "status",
            "is_featured",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_author(self, feedback) -> dict | None:
        user = feedback.author
        return {"id": user.id, "name": user.name, "phone": user.phone} if user else None

    def validate(self, attrs):
        def after(field, default=None):
            return attrs.get(field, getattr(self.instance, field, default))

        if self.instance is not None and self.instance.author_id:
            if (after("source"), after("course")) != (self.instance.source, self.instance.course):
                raise serializers.ValidationError({"source": "A student's feedback stays on what they rated."})
        validate_feedback(
            source=after("source"),
            course=after("course"),
            status=after("status", Feedback.Status.APPROVED),
            is_featured=after("is_featured", False),
        )
        return attrs
