from rest_framework import serializers

from apps.academic.models import Batch, ClassLevel
from apps.communication.models import Notice, NoticeCategory, SmsMessage
from apps.core.api.serializers.fields import HtmlField, MediaField

# The longest message staff may write: three SMS parts of Bangla text.
SMS_MAX_LENGTH = 480


class NoticeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = NoticeCategory
        fields = ["id", "title", "slug", "order"]
        read_only_fields = ["id"]


class AdminNoticeCategorySerializer(NoticeCategorySerializer):
    notice_count = serializers.IntegerField(read_only=True)

    class Meta(NoticeCategorySerializer.Meta):
        fields = [*NoticeCategorySerializer.Meta.fields, "notice_count"]


class NoticeSerializer(serializers.ModelSerializer):
    """`audience` names its class levels and batches; empty means everyone."""

    image = MediaField(required=False)
    body = HtmlField()
    categories = serializers.PrimaryKeyRelatedField(many=True, queryset=NoticeCategory.objects.all(), required=False)
    class_level_ids = serializers.PrimaryKeyRelatedField(
        source="class_levels", queryset=ClassLevel.objects.all(), many=True, required=False
    )
    batch_ids = serializers.PrimaryKeyRelatedField(
        source="batches", queryset=Batch.objects.all(), many=True, required=False
    )
    audience = serializers.SerializerMethodField()

    class Meta:
        model = Notice
        fields = [
            "id",
            "title",
            "body",
            "image",
            "categories",
            "class_level_ids",
            "batch_ids",
            "audience",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_audience(self, notice) -> list[str]:
        return [level.name for level in notice.class_levels.all()] + [batch.name for batch in notice.batches.all()]


class SmsMessageSerializer(serializers.ModelSerializer):
    to = serializers.SerializerMethodField()
    sent_by = serializers.SerializerMethodField()
    purpose_label = serializers.CharField(source="get_purpose_display")

    class Meta:
        model = SmsMessage
        fields = ["id", "created_at", "to", "phone", "purpose", "purpose_label", "body", "status", "error", "sent_by"]
        read_only_fields = fields

    def get_to(self, message) -> str:
        return "guardian" if message.purpose == SmsMessage.Purpose.GUARDIAN else "student"

    def get_sent_by(self, message) -> dict | None:
        user = message.sent_by
        return {"id": user.id, "name": user.name} if user else None


class StudentSmsRequestSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=["student", "guardian"])
    message = serializers.CharField(max_length=SMS_MAX_LENGTH, trim_whitespace=True)
