from django.db.models import Count

from apps.courses import selectors as course_selectors
from rest_framework import serializers

from apps.identity.models import User
from apps.core.api.fields import MediaField
from apps.assessment import content_exam
from apps.faculty.api.v1.serializers import PublicInstructorSerializer
from apps.assessment.models import Exam, QuestionBank

from apps.courses.models import Content, Course, CourseCategory, CourseMaterial, CoursePrice, Enrollment, Coupon, Routine, Section


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


def build_category_children(categories):
    """Group every descendant of `categories` by parent id, in one query.

    `CourseCategorySerializer` renders the tree recursively, so without this
    it spends one query per node just to ask whether that node has children
    -- a three-by-three tree cost 13 queries to return 12 rows, and the
    homepage paid it too. Pass the result as `context['category_children']`.
    """
    from collections import defaultdict

    frontier = [category.pk for category in categories]
    children = defaultdict(list)
    seen = set(frontier)

    # One query per depth level, not per node. Real trees are two or three
    # deep, and the `seen` guard means a cycle in the data terminates the
    # walk instead of hanging it.
    while frontier:
        rows = list(CourseCategory.objects.filter(category_id__in=frontier))
        for row in rows:
            children[row.category_id].append(row)
        frontier = [row.pk for row in rows if row.pk not in seen]
        seen.update(frontier)

    return children


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
        batched = self.context.get("category_children")
        # Without the batch this falls back to the per-node query, which is
        # what a single-object admin response wants anyway.
        kids = batched[obj.pk] if batched is not None else obj.children.all()
        return CourseCategorySerializer(kids, many=True, context=self.context).data


class CourseCategoryBadgeSerializer(serializers.ModelSerializer):
    """Slim category shape nested on a `Course` (list or detail) for badge
    rendering and client-side category filtering -- not the same as the
    standalone `CourseCategorySerializer` used for `/course-category` and
    the homepage's `courseCategories`, which also carries `children`/`order`."""

    image = MediaField(upload_to="course-category", required=False)

    class Meta:
        model = CourseCategory
        fields = ["id", "title", "slug", "image"]


def build_section_tree(course):
    """Every active section and content of `course`, grouped for the tree.

    The section serializer recurses, and each level used to ask the database
    for its own contents and its own sub-sections: two queries per section,
    however deep the tree went. A course with six sections and six
    sub-sections spent 26 of its 38 queries here, and the cost grew with
    every section an instructor added.

    Both maps are built from two queries covering the whole course. Pass
    them as `context['section_children']` / `context['section_contents']`.
    """
    from collections import defaultdict

    rows = list(Section.objects.filter(course=course, active=True))
    sections = defaultdict(list)
    for section in rows:
        sections[section.section_id].append(section)

    # Keyed on the section ids just found rather than on the course, so this
    # is exactly the union of the per-section queries it replaces -- a
    # content whose section belongs to another course is placed the same way
    # either way.
    contents = defaultdict(list)
    for content in Content.objects.filter(
        section_id__in=[section.pk for section in rows], active=True
    ):
        contents[content.section_id].append(content)

    return sections, contents


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
        batched = self.context.get("section_contents")
        rows = batched[obj.pk] if batched is not None else obj.contents.filter(active=True)
        return ContentListSerializer(rows, many=True, context=self.context).data

    def get_sub_sections(self, obj):
        batched = self.context.get("section_children")
        rows = batched[obj.pk] if batched is not None else obj.sub_sections.filter(active=True)
        return SectionSerializer(rows, many=True, context=self.context).data


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
        exam = getattr(obj, "exam", None)

        result = None
        if request and request.user.is_authenticated and exam is not None:
            from apps.assessment.models import ExamAttempt

            result = ExamAttempt.objects.filter(exam=exam, user=request.user).first()

        return {
            # Still the Content id: Exam uses it as its own primary key, so
            # this is the same number either way.
            "id": obj.id,
            "title": obj.title,
            "total_marks": exam and exam.total_marks,
            "pass_marks": exam and exam.pass_marks,
            "start_time": exam and exam.start_time,
            "end_time": exam and exam.end_time,
            "result_publish_time": exam and exam.result_publish_time,
            "duration": exam and exam.duration_minutes,
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
    """Content CRUD for the admin panel.

    The ten flat `exam_*` keys are contract but no longer live on Content --
    they moved to `assessment.Exam`. They are declared here explicitly and
    merged in and out through `apps.assessment.content_exam`, so the wire
    format is unchanged while the storage is not.
    """

    pdf_file = MediaField(upload_to="pdf", required=False)
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    section_id = serializers.PrimaryKeyRelatedField(source="section", queryset=Section.objects.all())

    exam_store_id = serializers.PrimaryKeyRelatedField(
        queryset=QuestionBank.objects.all(), required=False, allow_null=True
    )
    exam_mode = serializers.ChoiceField(
        choices=Exam.Mode.choices, required=False, default=Exam.Mode.EXAM
    )
    exam_total_marks = serializers.IntegerField(required=False, allow_null=True)
    exam_pass_marks = serializers.IntegerField(required=False, allow_null=True)
    # max_digits/decimal_places must match the model, or DRF renders 1.0
    # where the old payload said "1.00".
    exam_positive_marks = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    exam_negative_marks = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    exam_duration_minutes = serializers.IntegerField(required=False, allow_null=True)
    exam_start_time = serializers.DateTimeField(required=False, allow_null=True)
    exam_end_time = serializers.DateTimeField(required=False, allow_null=True)
    exam_result_publish_time = serializers.DateTimeField(required=False, allow_null=True)

    EXAM_KEYS = tuple(content_exam.FIELD_MAP)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        stored = content_exam.read_exam_fields(instance)
        for key in self.EXAM_KEYS:
            value = stored[key]
            if value is None or key == "exam_store_id":
                # exam_store_id is already the pk; the others need their
                # field's own rendering (decimals as "1.00", datetimes as
                # ISO strings).
                data[key] = value
            else:
                data[key] = self.fields[key].to_representation(value)
        return data

    def _pop_exam_values(self, validated_data):
        return {
            key: validated_data.pop(key)
            for key in list(self.EXAM_KEYS)
            if key in validated_data
        }

    def create(self, validated_data):
        exam_values = self._pop_exam_values(validated_data)
        content = super().create(validated_data)
        content_exam.write_exam_fields(content, exam_values)
        return content

    def update(self, instance, validated_data):
        exam_values = self._pop_exam_values(validated_data)
        content = super().update(instance, validated_data)
        content_exam.write_exam_fields(content, exam_values)
        return content

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


def build_course_stats(courses, request=None):
    """Batch every per-course aggregate the list serializer needs.

    Serialising a course used to cost 11 queries on its own -- six COUNTs for
    the per-type content totals, plus prices, categories, instructors,
    routines and the enrolment count -- so a page of 15 ran ~170 queries and
    the paginator's `per_page=200` ceiling meant ~2,200.

    Everything here is keyed by course id and resolved in a fixed number of
    queries regardless of page size. Pass the result to the serializer as
    `context['course_stats']`; without it the serializer falls back to the
    per-object queries, which is fine for a single course.
    """
    from collections import defaultdict

    ids = [course.pk for course in courses]
    if not ids:
        return {}

    content_counts = defaultdict(lambda: defaultdict(int))
    rows = (
        Content.objects.filter(course_id__in=ids)
        .values('course_id', 'type')
        .annotate(total=Count('id'))
    )
    for row in rows:
        content_counts[row['course_id']][row['type']] = row['total']

    prices = defaultdict(list)
    price_rows = CoursePrice.objects.filter(
        priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id__in=ids
    ).order_by('amount')
    for price in price_rows:
        prices[price.priceable_id].append(price)

    enrollment_counts = dict(
        Enrollment.objects.filter(course_id__in=ids)
        .values_list('course_id')
        .annotate(total=Count('id'))
    )

    enrollments, ordered = {}, set()
    if request is not None and request.user.is_authenticated:
        enrollments = {
            e.course_id: e
            for e in Enrollment.objects.filter(course_id__in=ids, user=request.user)
        }
        # `has_order` is a billing fact. Asking through the selector keeps
        # this app from importing the one that already points at it.
        ordered = course_selectors.ordered_course_ids(request.user, ids)

    return {
        'content_counts': content_counts,
        'prices': prices,
        'enrollment_counts': enrollment_counts,
        'enrollments': enrollments,
        'ordered': ordered,
    }


class CourseListSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)
    price = serializers.SerializerMethodField()
    categories = CourseCategoryBadgeSerializer(many=True, read_only=True)
    instructors = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    has_order = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    routines = RoutineSerializer(many=True, read_only=True)
    # Declared explicitly so they can read the batched totals instead of
    # firing the model properties' one-COUNT-each queries.
    video_count = serializers.SerializerMethodField()
    class_count = serializers.SerializerMethodField()
    exam_count = serializers.SerializerMethodField()
    note_count = serializers.SerializerMethodField()
    link_count = serializers.SerializerMethodField()
    live_count = serializers.SerializerMethodField()
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

    def _stats(self, key, obj, default=None):
        """Batched value for `obj` if the view supplied one, else None."""
        stats = self.context.get("course_stats")
        if not stats:
            return None
        return stats[key].get(obj.pk, default)

    def _content_count(self, obj, content_type):
        counts = self._stats("content_counts", obj, {})
        if counts is not None:
            return counts.get(content_type, 0)
        return obj.contents.filter(type=content_type).count()

    def get_video_count(self, obj):
        return self._content_count(obj, Content.Type.VIDEO)

    def get_exam_count(self, obj):
        return self._content_count(obj, Content.Type.EXAM)

    def get_note_count(self, obj):
        return self._content_count(obj, Content.Type.NOTE)

    def get_link_count(self, obj):
        return self._content_count(obj, Content.Type.LINK)

    def get_live_count(self, obj):
        return self._content_count(obj, Content.Type.LIVE)

    def get_class_count(self, obj):
        counts = self._stats("content_counts", obj, {})
        if counts is not None:
            return sum(counts.values())
        return obj.contents.count()

    def get_price(self, obj):
        batched = self._stats("prices", obj, [])
        if batched is not None:
            price = batched[0] if batched else None
        else:
            price = obj.prices.order_by("amount").first()
        return CoursePriceSerializer(price).data if price else None

    def get_instructors(self, obj):
        return PublicInstructorSerializer(obj.instructors.all(), many=True).data

    def _enrollment(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        stats = self.context.get("course_stats")
        if stats:
            return stats["enrollments"].get(obj.pk)
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

        stats = self.context.get("course_stats")
        if stats:
            return obj.pk in stats["ordered"]

        return obj.pk in course_selectors.ordered_course_ids(request.user, [obj.pk])

    def get_users_count(self, obj):
        batched = self._stats("enrollment_counts", obj, 0)
        if batched is not None:
            return batched
        return obj.enrollments.count()


class CourseDetailSerializer(CourseListSerializer):
    course_details = serializers.SerializerMethodField()
    prices = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    def get_prices(self, obj):
        # `build_course_stats` already fetched this course's prices, ordered
        # by amount, to pick the headline one for `price`.
        batched = self._stats("prices", obj, [])
        rows = batched if batched is not None else obj.prices.all()
        return CoursePriceSerializer(rows, many=True).data

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
        children, contents = build_section_tree(obj)
        context = {**self.context, "section_children": children, "section_contents": contents}
        # `children[None]` is the top level: sections with no parent.
        return SectionSerializer(children[None], many=True, context=context).data


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


class EnrollmentSerializer(serializers.ModelSerializer):
    """Matches the admin panel's real `Enrollment` shape, verified against
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
        model = Enrollment
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


class CourseMaterialSerializer(serializers.ModelSerializer):
    file = MediaField(upload_to="material", required=False)
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CourseMaterial
        fields = ["id", "title", "type", "course_id", "file", "created_at"]
        read_only_fields = ["id", "created_at"]
