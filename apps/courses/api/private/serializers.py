from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from apps.academic.models import Batch, ClassLevel, Group
from apps.core.api.serializers.fields import HtmlField, MediaField
from apps.courses import selectors, services
from apps.courses.api.serializers import CourseOwnedSerializer
from apps.courses.models import Content, Course, CourseTeacher, Enrollment, Section
from apps.courses.validators import (
    validate_content_type_change,
    validate_course,
    validate_section_stays_in_course,
    validate_valid_till_in_future,
)


class CourseOptionSerializer(serializers.ModelSerializer):
    """One choice in a course picker."""

    class Meta:
        model = Course
        fields = ["id", "title"]


class AdminCourseTeacherSerializer(serializers.ModelSerializer):
    """A teacher on a course; only `commission` and `order` are editable here."""

    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    # Only teacher accounts: a student assigned here would gain admin access to the course.
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=get_user_model()._default_manager.filter(teacher__isnull=False)
    )
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    designation = serializers.CharField(source="user.teacher.designation", read_only=True)
    description = serializers.CharField(source="user.teacher.description", read_only=True)
    institute = serializers.CharField(source="user.teacher.institute", read_only=True)
    type = serializers.CharField(source="user.teacher.type", read_only=True)
    image = MediaField(source="user.image", read_only=True)

    class Meta:
        model = CourseTeacher
        fields = [
            "id",
            "course_id",
            "user_id",
            "name",
            "email",
            "phone",
            "designation",
            "description",
            "institute",
            "type",
            "order",
            "commission",
            "image",
        ]
        read_only_fields = ["id"]
        validators = [
            UniqueTogetherValidator(
                queryset=CourseTeacher.objects.all(),
                fields=["course_id", "user_id"],
                message="This teacher is already on this course.",
            )
        ]


class AdminContentSerializer(CourseOwnedSerializer):
    note_body = HtmlField()
    video_description = HtmlField()
    exam = serializers.SerializerMethodField()
    pdf_file = MediaField(required=False)
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    section_id = serializers.PrimaryKeyRelatedField(source="section", queryset=Section.objects.all())

    class Meta:
        model = Content
        fields = [
            "id",
            "course_id",
            "section_id",
            "title",
            "type",
            "variant",
            "available_from",
            "paid",
            "active",
            "order",
            "video_source",
            "video_link",
            "video_description",
            "video_embedded",
            "video_cipher",
            "note_body",
            "pdf_file",
            "link_url",
            "live_url",
            "live_scheduled_at",
            "exam",
        ]
        read_only_fields = ["id"]

    def get_exam(self, obj) -> dict | None:
        return selectors.admin_lesson_exam(obj)

    def validate_type(self, value):
        validate_content_type_change(self.instance, value)
        return value


class AdminCourseSerializer(serializers.ModelSerializer):
    description = HtmlField()
    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all(), required=False, allow_null=True
    )
    class_level_name = serializers.CharField(source="class_level.name", read_only=True, default=None)
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.all(), required=False, allow_null=True
    )
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)
    batch_id = serializers.PrimaryKeyRelatedField(
        source="batch", queryset=Batch.objects.all(), required=False, allow_null=True
    )
    batch_name = serializers.CharField(source="batch.name", read_only=True, default=None)
    enrolled_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Course
        fields = [
            "id",
            "slug",
            "status",
            "published_at",
            "title",
            "subtitle",
            "summary",
            "description",
            "is_featured",
            "difficulty",
            "delivery",
            "is_online",
            "language",
            "duration",
            "fake_student_count",
            "enrolled_count",
            "class_level_id",
            "class_level_name",
            "group_id",
            "group_name",
            "batch_id",
            "batch_name",
            "starts_on",
            "ends_on",
            "enrollment_deadline",
            "schedule_note",
            "thumbnail",
            "banner",
            "promo_video",
            "syllabus_pdf",
            "learning_outcomes",
            "target_audience",
            "requirements",
            "highlights",
            "faqs",
            "meta_title",
            "meta_description",
            "og_image",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "published_at", "created_at", "updated_at"]

    def validate(self, attrs):
        validate_course(
            **{
                field: attrs[field] if field in attrs else getattr(self.instance, field, None)
                for field in ("class_level", "group", "batch", "starts_on", "ends_on")
            }
        )
        return attrs

    def create(self, validated_data):
        return services.create_course(validated_data, by=self.context["request"].user)


class AdminSectionSerializer(CourseOwnedSerializer):
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    section_id = serializers.PrimaryKeyRelatedField(
        source="section", queryset=Section.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Section
        fields = ["id", "course_id", "section_id", "title", "order", "active"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        validate_section_stays_in_course(self.instance, attrs.get("course"))
        return super().validate(attrs)

    def create(self, validated_data):
        return services.create_section(validated_data)


class SectionMoveSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=["up", "down"])


class ContentToggleSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=services.TOGGLEABLE_FLAGS, error_messages={"invalid_choice": "Must be `active` or `paid`."}
    )


class EnrollmentSerializer(serializers.ModelSerializer):
    """A student on a course: the user, with the enrolment under `pivot`."""

    id = serializers.IntegerField(source="user.id", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    role = serializers.CharField(source="user.role", read_only=True)
    pivot = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = ["id", "name", "email", "phone", "role", "pivot"]

    def get_pivot(self, obj) -> dict:
        return {
            "course_id": obj.course_id,
            "user_id": obj.user_id,
            "valid_till": obj.valid_till,
            "payment_type": obj.payment_type,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }


class AdminEnrollmentRequestSerializer(serializers.Serializer):
    """Names a course (`slugOrId` or `course_id`) and a student, plus what to set on the enrolment."""

    slugOrId = serializers.CharField(required=False)
    course_id = serializers.CharField(required=False)
    user_id = serializers.IntegerField(required=False)
    valid_till = serializers.DateTimeField(required=False, allow_null=True)
    payment_type = serializers.ChoiceField(choices=Enrollment.PaymentType.choices, required=False)

    def to_internal_value(self, data):
        if hasattr(data, "get") and data.get("valid_till") == "":
            data = {**{key: data.get(key) for key in data}, "valid_till": None}
        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs["course"] = selectors.course_by_slug_or_id(attrs.get("slugOrId") or attrs.get("course_id"))
        return attrs


class AdminEnrollmentCreateSerializer(AdminEnrollmentRequestSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs["course"] or not attrs.get("user_id"):
            raise serializers.ValidationError({"user_id": ["A valid course and user_id are required."]})
        attrs["user"] = get_user_model()._default_manager.filter(pk=attrs["user_id"]).first()
        if attrs["user"] is None:
            raise serializers.ValidationError({"user_id": ["No such user."]})
        validate_valid_till_in_future(attrs.get("valid_till"), timezone.now())
        return attrs
