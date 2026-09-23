from rest_framework import serializers

from apps.content.models import Advertisement, EBook, Notice, NoticeCategory, Page, Testimonial
from apps.core.api.fields import MediaField
from apps.profiles.api.private.serializers import TeacherSerializer


class NoticeCategorySerializer(serializers.ModelSerializer):
    notice_category_id = serializers.PrimaryKeyRelatedField(
        source="notice_category", queryset=NoticeCategory.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = NoticeCategory
        fields = ["id", "title", "slug", "notice_category_id", "order"]
        read_only_fields = ["id"]


class NoticeSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)
    categories = serializers.PrimaryKeyRelatedField(many=True, queryset=NoticeCategory.objects.all(), required=False)

    class Meta:
        model = Notice
        fields = ["id", "title", "slug", "body", "image", "categories", "created_at"]
        read_only_fields = ["id", "created_at"]


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


class EBookSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)
    # Admin's EBook type declares `preview: string | null` (unlike `image`,
    # which is `{id, link}`) and calls `.split("/")` on it directly -- a bare
    # `{id, link}` object here would break both the "view PDF" link and that
    # filename parsing.
    preview = MediaField(required=False, bare=True)

    class Meta:
        model = EBook
        fields = ["id", "title", "description", "booking_link", "preview", "image"]
        read_only_fields = ["id"]


class PageSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = Page
        fields = ["id", "key", "slug", "value_type", "value", "image", "video", "created_at", "updated_at"]
        read_only_fields = ["id", "key", "slug", "created_at", "updated_at"]


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
    """The landing page's eight payloads in one response.

    Fed by `apps.content.selectors.homepage_content`. The serializers for
    courses and categories are imported inside the methods: `courses` imports
    `content`, so pulling it in at module scope would close an import cycle.
    The roster's serializer needs no such dodge -- `profiles` is a lower layer.

    `suceesstorycounter` is spelled exactly like that on purpose -- the
    misspelling is what both frontends read, and is pinned by
    `apps/core/test_response_shapes.py`.
    """

    courses = serializers.SerializerMethodField()
    courseCategories = serializers.SerializerMethodField()
    advertisement = serializers.SerializerMethodField()
    testimonials = serializers.SerializerMethodField()
    counters = serializers.SerializerMethodField()
    suceesstorycounter = serializers.SerializerMethodField()
    instructors = serializers.SerializerMethodField()
    bannerImage = serializers.SerializerMethodField()

    def get_courses(self, data) -> list:
        from apps.courses.api.serializers import CourseListSerializer, build_course_stats

        request = self.context.get('request')
        courses = data['courses']
        return CourseListSerializer(
            courses,
            many=True,
            # The per-course aggregates are batched for the whole page; without
            # this the homepage costs several queries per course.
            context={'request': request, 'course_stats': build_course_stats(courses, request)},
        ).data

    def get_courseCategories(self, data) -> list:
        from apps.courses.api.serializers import (
            CourseCategorySerializer,
            build_category_children,
        )

        categories = data['categories']
        return CourseCategorySerializer(
            categories,
            many=True,
            context={'category_children': build_category_children(categories)},
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
