from rest_framework import serializers

from apps.accounts.models import User
from apps.core.fields import MediaField
from apps.exams.models import McqStore

from .models import Content, Course, CourseCategory, CoursePrice, CourseUser, Coupon, Instructor, Routine, Section


class CoursePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoursePrice
        fields = [
            "id",
            "priceable_type",
            "priceable_id",
            "title",
            "amount",
            "discount",
            "discount_till",
            "type",
            "validity_type",
            "validity_time",
            "validity_duration",
        ]
        read_only_fields = ["id"]


class CouponSerializer(serializers.ModelSerializer):
    price_id = serializers.PrimaryKeyRelatedField(source="price", queryset=CoursePrice.objects.all())

    class Meta:
        model = Coupon
        fields = ["id", "price_id", "code", "discount", "discount_type", "valid_till"]
        read_only_fields = ["id"]


class RoutineSerializer(serializers.ModelSerializer):
    link = MediaField(upload_to="routine", required=False)
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())

    class Meta:
        model = Routine
        fields = ["id", "course_id", "title", "link"]
        read_only_fields = ["id"]


class InstructorSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="instructor", required=False)
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=User.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Instructor
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


class PublicInstructorSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)

    class Meta:
        model = Instructor
        fields = ["id", "name", "designation", "description", "type", "order", "image"]


class CourseCategorySerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="course-category", required=False)
    course_category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=CourseCategory.objects.all(), required=False, allow_null=True
    )
    children = serializers.SerializerMethodField()

    class Meta:
        model = CourseCategory
        fields = ["id", "title", "slug", "image", "course_category_id", "order", "children"]
        read_only_fields = ["id", "slug"]

    def get_children(self, obj):
        return CourseCategorySerializer(obj.children.all(), many=True, context=self.context).data


class CourseCategoryBadgeSerializer(serializers.ModelSerializer):
    """Slim category shape nested on a `Course` (list or detail) for badge
    rendering and client-side category filtering -- not the same as the
    standalone `CourseCategorySerializer` used for `/course-category` and
    the homepage's `courseCategories`, which also carries `children`/`order`."""

    image = MediaField(upload_to="course-category", required=False)

    class Meta:
        model = CourseCategory
        fields = ["id", "title", "slug", "image"]


class SectionSerializer(serializers.ModelSerializer):
    course_id = serializers.PrimaryKeyRelatedField(source="course", read_only=True)
    section_id = serializers.PrimaryKeyRelatedField(source="section", read_only=True)
    contents = serializers.SerializerMethodField()
    sub_sections = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            "id",
            "course_id",
            "section_id",
            "title",
            "slug",
            "order",
            "active",
            "contents",
            "sub_sections",
        ]
        read_only_fields = ["id", "slug"]

    def get_contents(self, obj):
        return ContentListSerializer(obj.contents.filter(active=True), many=True, context=self.context).data

    def get_sub_sections(self, obj):
        return SectionSerializer(obj.sub_sections.filter(active=True), many=True, context=self.context).data


class ContentListSerializer(serializers.ModelSerializer):
    """Lightweight shape used inside a course's section tree -- no answer
    keys / full resource payload, just enough to render the lesson list."""

    class Meta:
        model = Content
        fields = ["id", "title", "slug", "type", "variant", "paid", "available_from", "order"]


class ContentDetailSerializer(serializers.ModelSerializer):
    """Full per-lesson payload returned by GET /content/{slug} -- shaped to
    match the discriminated-union `video|pdf|exam|link` structure the
    client's `ContentDetail` type expects."""

    course_id = serializers.PrimaryKeyRelatedField(source="course", read_only=True)
    section_id = serializers.PrimaryKeyRelatedField(source="section", read_only=True)
    video = serializers.SerializerMethodField()
    pdf = serializers.SerializerMethodField()
    exam = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            "id",
            "title",
            "slug",
            "type",
            "paid",
            "course_id",
            "section_id",
            "available_from",
            "video",
            "pdf",
            "exam",
            "link",
        ]

    def get_video(self, obj):
        if obj.type != Content.Type.VIDEO:
            return None
        return {
            "id": obj.id,
            "title": obj.title,
            "source": obj.video_source,
            "link": obj.video_link,
            "description": obj.video_description,
            "embedded": obj.video_embedded,
            "cipher": obj.video_cipher,
        }

    def get_pdf(self, obj):
        if obj.type != Content.Type.PDF:
            return None
        return {"id": obj.id, "title": obj.title, "link": obj.pdf_file}

    def get_exam(self, obj):
        if obj.type != Content.Type.EXAM:
            return None
        request = self.context.get("request")
        result = None
        if request and request.user.is_authenticated:
            from apps.exams.models import ExamResult

            result = ExamResult.objects.filter(content=obj, user=request.user).first()
        return {
            "id": obj.id,
            "title": obj.title,
            "total_marks": obj.exam_total_marks,
            "pass_marks": obj.exam_pass_marks,
            "start_time": obj.exam_start_time,
            "end_time": obj.exam_end_time,
            "result_publish_time": obj.exam_result_publish_time,
            "duration": obj.exam_duration_minutes,
            "submitted": bool(result),
        }

    def get_link(self, obj):
        if obj.type not in (Content.Type.LINK, Content.Type.LIVE, Content.Type.NOTE):
            return None
        if obj.type == Content.Type.LINK:
            return obj.link_url
        if obj.type == Content.Type.LIVE:
            return obj.live_url
        return obj.note_body


class AdminContentSerializer(serializers.ModelSerializer):
    pdf_file = MediaField(upload_to="pdf", required=False)
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    section_id = serializers.PrimaryKeyRelatedField(source="section", queryset=Section.objects.all())
    exam_store_id = serializers.PrimaryKeyRelatedField(
        source="exam_store", queryset=McqStore.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Content
        fields = [
            "id",
            "course_id",
            "section_id",
            "title",
            "slug",
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
            "exam_store_id",
            "exam_mode",
            "exam_total_marks",
            "exam_pass_marks",
            "exam_positive_marks",
            "exam_negative_marks",
            "exam_duration_minutes",
            "exam_start_time",
            "exam_end_time",
            "exam_result_publish_time",
        ]
        read_only_fields = ["id", "slug"]


class CourseListSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)
    price = serializers.SerializerMethodField()
    categories = CourseCategoryBadgeSerializer(many=True, read_only=True)
    instructors = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    has_order = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    routines = RoutineSerializer(many=True, read_only=True)
    # No "audio" content type or online/offline content distinction is
    # modeled yet -- stubbed to 0 so the client's `Course` type is satisfied
    # without breaking anything that reads these fields.
    audio_count = serializers.SerializerMethodField()
    online_count = serializers.SerializerMethodField()
    offline_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "subtitle",
            "duration",
            "is_online",
            "active",
            "featured",
            "fake_user_count",
            "video_count",
            "class_count",
            "exam_count",
            "note_count",
            "link_count",
            "live_count",
            "audio_count",
            "online_count",
            "offline_count",
            "image",
            "price",
            "categories",
            "instructors",
            "routines",
            "subscription_status",
            "has_order",
            "users_count",
        ]

    def get_audio_count(self, obj):
        return 0

    def get_online_count(self, obj):
        return 0

    def get_offline_count(self, obj):
        return 0

    def get_price(self, obj):
        price = obj.prices.order_by("amount").first()
        return CoursePriceSerializer(price).data if price else None

    def get_instructors(self, obj):
        return PublicInstructorSerializer(obj.instructors.all(), many=True).data

    def _enrollment(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        return obj.enrollments.filter(user=request.user).first()

    def get_subscription_status(self, obj):
        from django.utils import timezone

        enrollment = self._enrollment(obj)
        if not enrollment:
            return None
        status = "active"
        if enrollment.valid_till and enrollment.valid_till < timezone.now():
            status = "expired"
        return {
            "status": status,
            "valid_till": enrollment.valid_till,
            "payment_type": enrollment.payment_type,
        }

    def get_has_order(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        from apps.shop.models import Order

        return Order.objects.filter(user=request.user, course=obj).exists()

    def get_users_count(self, obj):
        return obj.enrollments.count()


class CourseDetailSerializer(CourseListSerializer):
    course_details = serializers.SerializerMethodField()
    prices = CoursePriceSerializer(many=True, read_only=True)
    sections = serializers.SerializerMethodField()

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            "course_details",
            "prices",
            "sections",
        ]

    def get_course_details(self, obj):
        return {
            "description": obj.description,
            "features": obj.features,
            "video": obj.video,
            "pdf_link": obj.pdf_link,
        }

    def get_sections(self, obj):
        top_level = obj.sections.filter(section__isnull=True, active=True)
        return SectionSerializer(top_level, many=True, context=self.context).data


class AdminCourseSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="course", required=False)
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=CourseCategory.objects.all(), required=False
    )

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "subtitle",
            "slug",
            "duration",
            "is_online",
            "active",
            "featured",
            "fake_user_count",
            "description",
            "features",
            "video",
            "pdf_link",
            "image",
            "categories",
        ]
        read_only_fields = ["id", "slug"]


class AdminSectionSerializer(serializers.ModelSerializer):
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    section_id = serializers.PrimaryKeyRelatedField(
        source="section", queryset=Section.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Section
        fields = ["id", "course_id", "section_id", "title", "slug", "order", "active"]
        read_only_fields = ["id", "slug"]


class CourseUserSerializer(serializers.ModelSerializer):
    """Matches the admin panel's real `CourseUser` shape, verified against
    its own page source: a flat user record with the enrollment nested
    under `pivot` -- the inverse of the more obvious pivot-wraps-user
    shape, but that's what `app/(dashboard)/course/[id]/users/page.tsx`
    actually reads (`row.name`, `row.pivot.valid_till`, ...)."""

    id = serializers.IntegerField(source="user.id", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    role = serializers.CharField(source="user.role", read_only=True)
    pivot = serializers.SerializerMethodField()

    class Meta:
        model = CourseUser
        fields = ["id", "name", "email", "phone", "role", "pivot"]

    def get_pivot(self, obj):
        return {
            "course_id": obj.course_id,
            "user_id": obj.user_id,
            "valid_till": obj.valid_till,
            "payment_type": obj.payment_type,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
