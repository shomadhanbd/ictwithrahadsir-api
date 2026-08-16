from rest_framework import serializers

from apps.core.api.fields import MediaField
from apps.courses.models import Course

from .models import Advertisement, Counter, CourseMaterial, ContactMessage, EBook, Notice, NoticeCategory, Page, Testimonial


class NoticeCategorySerializer(serializers.ModelSerializer):
    notice_category_id = serializers.PrimaryKeyRelatedField(
        source="notice_category", queryset=NoticeCategory.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = NoticeCategory
        fields = ["id", "title", "slug", "notice_category_id", "order"]
        read_only_fields = ["id", "slug"]


class NoticeSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="notice", required=False)
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=NoticeCategory.objects.all(), required=False
    )

    class Meta:
        model = Notice
        fields = ["id", "title", "slug", "body", "image", "categories", "created_at"]
        read_only_fields = ["id", "slug", "created_at"]


class TestimonialSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="testimonial", required=False)

    class Meta:
        model = Testimonial
        fields = ["id", "name", "designation", "description", "ratings", "image"]
        read_only_fields = ["id"]


class AdvertisementSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="advertisement", required=False)

    class Meta:
        model = Advertisement
        fields = ["id", "title", "description", "link", "type", "image"]
        read_only_fields = ["id"]


class EBookSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="ebook", required=False)
    # Admin's EBook type declares `preview: string | null` (unlike `image`,
    # which is `{id, link}`) and calls `.split("/")` on it directly -- a bare
    # `{id, link}` object here would break both the "view PDF" link and that
    # filename parsing.
    preview = MediaField(upload_to="ebook", required=False, bare=True)

    class Meta:
        model = EBook
        fields = ["id", "title", "description", "booking_link", "preview", "image"]
        read_only_fields = ["id"]


class CourseMaterialSerializer(serializers.ModelSerializer):
    file = MediaField(upload_to="material", required=False)
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CourseMaterial
        fields = ["id", "title", "type", "course_id", "file", "created_at"]
        read_only_fields = ["id", "created_at"]


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

    def get_user(self, obj):
        if not obj.user:
            return None
        return {"id": obj.user.id, "name": obj.user.name, "phone": obj.user.phone}


class PageSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="page", required=False)

    class Meta:
        model = Page
        fields = ["id", "key", "slug", "value_type", "value", "image", "video", "created_at", "updated_at"]
        read_only_fields = ["id", "key", "slug", "created_at", "updated_at"]


class CounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Counter
        fields = ["id", "key", "label", "value"]


class HomeCounterSerializer(serializers.ModelSerializer):
    """Homepage stat counters are managed as `Page` rows (value_type="counter")
    through the admin panel's Pages screen, not the unused `Counter` model."""

    class Meta:
        model = Page
        fields = ["id", "key", "value", "slug"]


class HomeBannerSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="page", required=False)

    class Meta:
        model = Page
        fields = ["id", "key", "image"]
