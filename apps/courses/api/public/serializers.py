from rest_framework import serializers

from apps.core.api.serializers.fields import MediaField
from apps.courses import selectors
from apps.courses.api.serializers import RoutineSerializer
from apps.courses.models import Content, Course, CourseTeacher, Section


class CourseInstructorSerializer(serializers.ModelSerializer):
    """A teacher on a course, under the public `instructors` key."""

    name = serializers.CharField(source="user.name", read_only=True)
    designation = serializers.CharField(source="user.teacher.designation", read_only=True)
    description = serializers.CharField(source="user.teacher.description", read_only=True)
    type = serializers.CharField(source="user.teacher.type", read_only=True)
    image = MediaField(source="user.image", read_only=True)

    class Meta:
        model = CourseTeacher
        fields = ["id", "name", "designation", "description", "type", "order", "image"]


class ContentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "type", "variant", "paid", "available_from", "order"]


class SectionSerializer(serializers.ModelSerializer):
    """One curriculum section; needs `section_children` and `section_contents` from `selectors.section_tree`."""

    course_id = serializers.PrimaryKeyRelatedField(source="course", read_only=True)
    section_id = serializers.PrimaryKeyRelatedField(source="section", read_only=True)
    contents = serializers.SerializerMethodField()
    sub_sections = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ["id", "course_id", "section_id", "title", "order", "active", "contents", "sub_sections"]
        read_only_fields = ["id"]

    def get_contents(self, obj):
        return ContentListSerializer(self.context["section_contents"][obj.pk], many=True, context=self.context).data

    def get_sub_sections(self, obj):
        return SectionSerializer(self.context["section_children"][obj.pk], many=True, context=self.context).data


class ContentDetailSerializer(serializers.ModelSerializer):
    """One lesson; the block matching its `type` is filled, the rest are null."""

    course_id = serializers.PrimaryKeyRelatedField(source="course", read_only=True)
    section_id = serializers.PrimaryKeyRelatedField(source="section", read_only=True)
    video = serializers.SerializerMethodField()
    note = serializers.SerializerMethodField()
    pdf = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()
    live = serializers.SerializerMethodField()
    exam = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            "id",
            "title",
            "type",
            "variant",
            "paid",
            "course_id",
            "section_id",
            "available_from",
            "video",
            "note",
            "pdf",
            "link",
            "live",
            "exam",
        ]

    def get_video(self, obj) -> dict | None:
        if obj.type != Content.Type.VIDEO:
            return None
        return {
            "source": obj.video_source,
            "link": obj.video_link,
            "description": obj.video_description,
            "embedded": obj.video_embedded,
            "cipher": obj.video_cipher,
        }

    def get_note(self, obj) -> dict | None:
        return {"body": obj.note_body} if obj.type == Content.Type.NOTE else None

    def get_pdf(self, obj) -> dict | None:
        return {"url": obj.pdf_file} if obj.type == Content.Type.PDF else None

    def get_link(self, obj) -> dict | None:
        return {"url": obj.link_url} if obj.type == Content.Type.LINK else None

    def get_live(self, obj) -> dict | None:
        if obj.type != Content.Type.LIVE:
            return None
        return {"url": obj.live_url, "scheduled_at": obj.live_scheduled_at}

    def get_exam(self, obj) -> dict | None:
        if obj.type != Content.Type.EXAM:
            return None
        request = self.context.get("request")
        return selectors.lesson_exam(obj, request.user if request else None)


class AudienceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()


class CoursePackageSerializer(serializers.Serializer):
    """A package the course is sold in. No access_days or access_ends_on means lifetime."""

    id = serializers.IntegerField()
    product_id = serializers.CharField(help_text="Pass to /public/payments/initiate/.")
    title = serializers.CharField()
    price = serializers.IntegerField()
    base_price = serializers.IntegerField()
    discount_ends_at = serializers.DateTimeField(allow_null=True)
    access_days = serializers.IntegerField(allow_null=True)
    access_ends_on = serializers.DateField(allow_null=True)
    course_count = serializers.IntegerField(help_text="More than 1 means a bundle.")


class CourseListSerializer(serializers.ModelSerializer):
    """A course card; needs `course_stats` from `selectors.course_card_stats` in the context."""

    class_level = AudienceSerializer(read_only=True, allow_null=True)
    group = AudienceSerializer(read_only=True, allow_null=True)
    batch = AudienceSerializer(read_only=True, allow_null=True)
    student_count = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    is_free = serializers.SerializerMethodField()
    instructors = CourseInstructorSerializer(many=True, read_only=True)
    enrollment_open = serializers.BooleanField(read_only=True)
    lesson_counts = serializers.SerializerMethodField()
    enrollment = serializers.SerializerMethodField()
    has_purchased = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "slug",
            "title",
            "subtitle",
            "summary",
            "thumbnail",
            "delivery",
            "is_online",
            "difficulty",
            "language",
            "duration",
            "class_level",
            "group",
            "batch",
            "is_featured",
            "student_count",
            "price",
            "is_free",
            "instructors",
            "starts_on",
            "enrollment_open",
            "lesson_counts",
            "enrollment",
            "has_purchased",
        ]

    def _stats(self, key, obj, default=None):
        return self.context["course_stats"][key].get(obj.pk, default)

    def get_lesson_counts(self, obj) -> dict:
        counts = self._stats("content_counts", obj, {})
        by_type = {content_type: counts.get(content_type, 0) for content_type in Content.Type.values}
        return {**by_type, "total": sum(by_type.values())}

    def get_student_count(self, obj) -> int:
        """Real enrolments plus the admin's display padding."""
        return self._stats("enrollment_counts", obj, 0) + obj.fake_student_count

    def get_price(self, obj) -> dict | None:
        """The cheapest package on sale, or null when the course is not for sale."""
        packages = self._stats("packages", obj, [])
        return CoursePackageSerializer(packages[0]).data if packages else None

    def get_is_free(self, obj) -> bool:
        return any(package["price"] == 0 for package in self._stats("packages", obj, []))

    def get_enrollment(self, obj) -> dict | None:
        enrollment = self._stats("enrollments", obj)
        if enrollment is None:
            return None
        return {
            "status": enrollment.status,
            "valid_till": enrollment.valid_till,
            "payment_type": enrollment.payment_type,
            "renewable": selectors.renewable(enrollment),
        }

    def get_has_purchased(self, obj) -> bool:
        return obj.pk in self.context["course_stats"]["ordered"]


class ScheduleSerializer(serializers.Serializer):
    starts_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    enrollment_deadline = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField(source="schedule_note")


class SeoSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    image = serializers.URLField(allow_null=True)


class CourseDetailSerializer(CourseListSerializer):
    """The course landing page: the card plus everything that sells it."""

    schedule = serializers.SerializerMethodField()
    routines = RoutineSerializer(many=True, read_only=True)
    packages = serializers.SerializerMethodField()
    curriculum = serializers.SerializerMethodField()
    seo = SeoSerializer(read_only=True)

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            "status",
            "description",
            "banner",
            "promo_video",
            "syllabus_pdf",
            "learning_outcomes",
            "target_audience",
            "requirements",
            "highlights",
            "faqs",
            "schedule",
            "routines",
            "packages",
            "curriculum",
            "seo",
        ]

    def get_schedule(self, obj) -> dict:
        return ScheduleSerializer(obj).data

    def get_packages(self, obj) -> list:
        """Every package on sale that includes this course, cheapest first."""
        return CoursePackageSerializer(self._stats("packages", obj, []), many=True).data

    def get_curriculum(self, obj) -> list:
        children, contents = selectors.section_tree(obj)
        context = {**self.context, "section_children": children, "section_contents": contents}
        return SectionSerializer(children[None], many=True, context=context).data


class CourseProgressSerializer(serializers.Serializer):
    completed_content_ids = serializers.ListField(child=serializers.IntegerField())
    completed = serializers.IntegerField()
    total = serializers.IntegerField()
    percent = serializers.IntegerField()


class ContentCompletionRequestSerializer(serializers.Serializer):
    content_id = serializers.IntegerField()
