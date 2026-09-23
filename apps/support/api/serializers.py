from rest_framework import serializers

from apps.support.models import ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    """`reply` is what the public client's dashboard support view reads
    (`msg.reply`); `reply_message` is what the admin panel's contacts page
    reads/writes (`contact.reply_message`) -- both names are exposed for the
    same underlying field since the two frontends disagree on the name."""

    user = serializers.SerializerMethodField()
    reply = serializers.CharField(source="reply_message", read_only=True, allow_blank=True)
    reply_message = serializers.CharField(read_only=True, allow_blank=True)

    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "user",
            "name",
            "phone",
            "email",
            "subject",
            "message",
            "reply",
            "reply_message",
            "is_read",
            "created_at",
        ]
        read_only_fields = ["id", "user", "reply", "is_read", "created_at"]

    def get_user(self, obj) -> dict | None:
        if not obj.user:
            return None
        return {"id": obj.user.id, "name": obj.user.name, "phone": obj.user.phone}


class ContactReplyRequestSerializer(serializers.Serializer):
    reply_message = serializers.CharField()
