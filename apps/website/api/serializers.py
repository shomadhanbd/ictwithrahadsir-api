from rest_framework import serializers

from apps.core.api.serializers.fields import MediaField
from apps.courses.api.public.serializers import CourseListSerializer
from apps.courses.selectors import course_card_stats
from apps.feedback.api.serializers import HomeTestimonialSerializer
from apps.profiles.api.public.serializers import TeacherSerializer
from apps.website.models import Banner
from apps.website.validators import validate_banner_dates, validate_link


def field_spec(field) -> dict:
    """A field as the admin's form builder reads it."""
    spec = {"name": field.name, "label": field.label, "type": field.type, "required": field.required}
    if field.help:
        spec["help"] = field.help
    if field.choices:
        spec["choices"] = [{"value": value, "label": label} for value, label in field.choices]
    if field.type == "list":
        spec["fields"] = [field_spec(f) for f in field.fields]
        spec["max_items"] = field.max_items
    return spec


class AdminSectionSerializer(serializers.Serializer):
    """A `selectors.SectionState`: the section's form and its current content."""

    def to_representation(self, state):
        spec = state.spec
        return {
            "key": spec.key,
            "page": spec.page,
            "title": spec.title,
            "description": spec.description,
            "can_hide": spec.can_hide,
            "fields": [field_spec(f) for f in spec.fields],
            "content": state.content,
            "is_visible": state.is_visible,
            "updated_at": state.updated_at,
        }


class SectionUpdateSerializer(serializers.Serializer):
    content = serializers.JSONField(required=False)
    is_visible = serializers.BooleanField(required=False)


class BannerSerializer(serializers.ModelSerializer):
    image = MediaField(bare=True, max_length=500)

    class Meta:
        model = Banner
        fields = ["id", "title", "image", "link"]


class AdminBannerSerializer(serializers.ModelSerializer):
    image = MediaField(bare=True, max_length=500, required=True, allow_null=False)

    class Meta:
        model = Banner
        fields = ["id", "title", "image", "link", "is_active", "order", "starts_at", "ends_at", "created_at"]
        read_only_fields = ["id", "order", "created_at"]

    def validate_link(self, value):
        if value:
            validate_link(value)
        return value

    def validate(self, attrs):
        def after(field):
            return attrs.get(field, getattr(self.instance, field, None))

        validate_banner_dates(starts_at=after("starts_at"), ends_at=after("ends_at"))
        return attrs


class MoveSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=["up", "down"])


class StatSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.CharField()


class HomeSerializer(serializers.Serializer):
    """The home page's live data; its copy comes from `/public/website/`."""

    courses = serializers.SerializerMethodField()
    banners = BannerSerializer(many=True)
    testimonials = HomeTestimonialSerializer(many=True)
    stats = StatSerializer(many=True)
    instructors = TeacherSerializer(many=True)

    def get_courses(self, data) -> list:
        request = self.context.get("request")
        user = request.user if request else None
        courses = data["courses"]
        context = {"request": request, "course_stats": course_card_stats(courses, user)}
        return CourseListSerializer(courses, many=True, context=context).data
