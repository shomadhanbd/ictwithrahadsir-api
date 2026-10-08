from rest_framework import serializers

from apps.content.models import Advertisement, Page, Testimonial
from apps.core.api.serializers.fields import MediaField
from apps.core.text.html import clean_html
from apps.profiles.api.public.serializers import TeacherSerializer


class TestimonialSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = Testimonial
        fields = ["id", "name", "designation", "description", "ratings", "image"]
        read_only_fields = ["id"]


class AdvertisementSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = Advertisement
        fields = ["id", "title", "description", "link", "type", "image"]
        read_only_fields = ["id"]


class PageSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = Page
        fields = ["id", "key", "slug", "value_type", "value", "image", "video", "created_at", "updated_at"]
        # A page's type is fixed when it is seeded: changing it would let raw markup in as "image" and then
        # be served as HTML, and would drop the home banner or counters out of `/home`.
        read_only_fields = ["id", "key", "slug", "value_type", "created_at", "updated_at"]

    def validate(self, attrs):
        value_type = getattr(self.instance, "value_type", Page.ValueType.HTML)
        if value_type == Page.ValueType.HTML and attrs.get("value"):
            attrs["value"] = clean_html(attrs["value"])
        return attrs


class HomeCounterSerializer(serializers.ModelSerializer):
    """Homepage stat counters are managed as `Page` rows (value_type="counter")
    through the admin panel's Pages screen, not the unused `Counter` model."""

    class Meta:
        model = Page
        fields = ["id", "key", "value", "slug"]


class HomeBannerSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = Page
        fields = ["id", "key", "image"]


class HomeSerializer(serializers.Serializer):
    """The landing page's seven payloads in one response.

    Fed by `apps.content.selectors.homepage_content`. The course serializer
    is imported inside the method: `courses` imports
    `content`, so pulling it in at module scope would close an import cycle.
    The roster's serializer needs no such dodge -- `profiles` is a lower layer.

    `suceesstorycounter` is spelled exactly like that on purpose -- the
    misspelling is what both frontends read, and is pinned by
    `apps/core/tests/test_response_shapes.py`.
    """

    courses = serializers.SerializerMethodField()
    advertisement = serializers.SerializerMethodField()
    testimonials = serializers.SerializerMethodField()
    counters = serializers.SerializerMethodField()
    suceesstorycounter = serializers.SerializerMethodField()
    instructors = serializers.SerializerMethodField()
    bannerImage = serializers.SerializerMethodField()

    def get_courses(self, data) -> list:
        from apps.courses.api.public.serializers import CourseListSerializer
        from apps.courses.selectors import course_card_stats

        request = self.context.get('request')
        courses = list(data['courses'])
        user = request.user if request else None
        return CourseListSerializer(
            courses, many=True, context={'request': request, 'course_stats': course_card_stats(courses, user)}
        ).data

    def get_advertisement(self, data) -> list:
        return AdvertisementSerializer(data['advertisements'], many=True).data

    def get_testimonials(self, data) -> list:
        return TestimonialSerializer(data['testimonials'], many=True).data

    def get_counters(self, data) -> list:
        return HomeCounterSerializer(data['counters'], many=True).data

    def get_suceesstorycounter(self, data) -> int | str | None:
        return data['success_story']

    def get_instructors(self, data) -> list:
        return TeacherSerializer(data['instructors'], many=True).data

    def get_bannerImage(self, data) -> dict | None:
        banner = data['banner']
        return HomeBannerSerializer(banner).data if banner else None
