from django.contrib.auth import get_user_model
from django.db.models import Count

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from apps.core.api.fields import MediaField
from apps.courses import selectors as course_selectors
from apps.courses.models import (
    Content,
    Coupon,
    Course,
    CourseCategory,
    CourseMaterial,
    CoursePrice,
    CourseTeacher,
    Enrollment,
    Routine,
    Section,
)


class PublicTeacherSerializer(serializers.ModelSerializer):
    """The teacher block inside a course payload.

    Emitted under the key `instructors`, which is a frozen public contract --
    both frontends and any mobile client read it. Everything else in the
    codebase calls this person a teacher.

    `id` and `order` are the assignment's -- a teacher can sit in a different
    position on each course. Everything else is read through the roster, which
    keeps this key-for-key identical to `profiles.TeacherSerializer`, as
    `test_response_shapes.PUBLIC_TEACHER_KEYS` demands of both.
    """

    name = serializers.CharField(source="user.name", read_only=True)
    designation = serializers.CharField(source="user.teacher.designation", read_only=True)
    description = serializers.CharField(source="user.teacher.description", read_only=True)
    type = serializers.CharField(source="user.teacher.type", read_only=True)
    image = MediaField(source="user.image", read_only=True)

    class Meta:
        model = CourseTeacher
        fields = ["id", "name", "designation", "description", "type", "order", "image"]


class AdminCourseTeacherSerializer(serializers.ModelSerializer):
    """A teacher's assignment to one course, as the admin panel edits it.

    Only `commission` and `order` are the assignment's own. The flat keys below
    are the teacher's, kept read-only so the panel's table renders from one
    request; editing them is the Teachers page's job.
    """

    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    #: Only accounts holding a roster entry: assigning a plain student would
    #: hand them that course's admin scope.
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
    link = MediaField(required=False)
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
    image = MediaField(required=False)
    course_category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=CourseCategory.objects.all(), required=False, allow_null=True
    )
    children = serializers.SerializerMethodField()

    class Meta:
        model = CourseCategory
        fields = ["id", "title", "slug", "image", "course_category_id", "order", "children"]
        read_only_fields = ["id"]

    def get_children(self, obj) -> list:
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

    image = MediaField(required=False)

    class Meta:
        model = CourseCategory
        fields = ["id", "title", "slug", "image"]


def build_section_tree(course):
    """Every active section and content of `course`, grouped for the tree.

    The section serializer recurses, and each level used to ask the database
    for its own contents and its own sub-sections: two queries per section,
    however deep the tree went. A course with six sections and six
    sub-sections spent 26 of its 38 queries here, and the cost grew with
    every section a teacher added.

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
    for content in Content.objects.filter(section_id__in=[section.pk for section in rows], active=True):
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

    def get_video(self, obj) -> dict | None:
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

    def get_pdf(self, obj) -> dict | None:
        if obj.type != Content.Type.PDF:
            return None
        return {"id": obj.id, "title": obj.title, "link": obj.pdf_file}

    def get_exam(self, obj) -> dict | None:
        """The paper attached to a lesson, once there is somewhere to store one.

        The legacy `assessment` app that held these rows has been removed and
        `apps.exam` is authoring-only, with no student-facing delivery yet. The
        key stays on the wire so the shape does not change under the clients;
        it reports the lesson and nothing else until the new app can answer.
        """
        if obj.type != Content.Type.EXAM:
            return None

        return {
            "id": obj.id,
            "title": obj.title,
            "total_marks": None,
            "pass_marks": None,
            "start_time": None,
            "end_time": None,
            "result_publish_time": None,
            "duration": None,
            "submitted": False,
        }

    def get_link(self, obj) -> dict | None:
        if obj.type not in (Content.Type.LINK, Content.Type.LIVE, Content.Type.NOTE):
            return None
        if obj.type == Content.Type.LINK:
            return obj.link_url
        if obj.type == Content.Type.LIVE:
            return obj.live_url
        return obj.note_body


class AdminContentSerializer(serializers.ModelSerializer):
    """Content CRUD for the admin panel.

    It used to carry ten flat `exam_*` keys, stored on `assessment.Exam` and
    merged in and out on the way past. That app has been removed; when the
    replacement built on `apps.exam` can hold a lesson's paper, this is where
    it attaches.
    """

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
        ]
        read_only_fields = ["id"]


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
    rows = Content.objects.filter(course_id__in=ids).values('course_id', 'type').annotate(total=Count('id'))
    for row in rows:
        content_counts[row['course_id']][row['type']] = row['total']

    prices = defaultdict(list)
    price_rows = CoursePrice.objects.filter(priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id__in=ids).order_by(
        'amount'
    )
    for price in price_rows:
        prices[price.priceable_id].append(price)

    enrollment_counts = dict(
        Enrollment.objects.filter(course_id__in=ids).values_list('course_id').annotate(total=Count('id'))
    )

    enrollments, ordered = {}, set()
    if request is not None and request.user.is_authenticated:
        enrollments = {e.course_id: e for e in Enrollment.objects.filter(course_id__in=ids, user=request.user)}
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

    def get_audio_count(self, obj) -> int:
        return 0

    def get_online_count(self, obj) -> int:
        return 0

    def get_offline_count(self, obj) -> int:
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

    def get_video_count(self, obj) -> int:
        return self._content_count(obj, Content.Type.VIDEO)

    def get_exam_count(self, obj) -> int:
        return self._content_count(obj, Content.Type.EXAM)

    def get_note_count(self, obj) -> int:
        return self._content_count(obj, Content.Type.NOTE)

    def get_link_count(self, obj) -> int:
        return self._content_count(obj, Content.Type.LINK)

    def get_live_count(self, obj) -> int:
        return self._content_count(obj, Content.Type.LIVE)

    def get_class_count(self, obj) -> int:
        counts = self._stats("content_counts", obj, {})
        if counts is not None:
            return sum(counts.values())
        return obj.contents.count()

    def get_price(self, obj) -> dict | None:
        batched = self._stats("prices", obj, [])
        if batched is not None:
            price = batched[0] if batched else None
        else:
            price = obj.prices.order_by("amount").first()
        return CoursePriceSerializer(price).data if price else None

    def get_instructors(self, obj) -> list:
        return PublicTeacherSerializer(obj.instructors.all(), many=True).data

    def _enrollment(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        stats = self.context.get("course_stats")
        if stats:
            return stats["enrollments"].get(obj.pk)
        return obj.enrollments.filter(user=request.user).first()

    def get_subscription_status(self, obj) -> dict | None:
        enrollment = self._enrollment(obj)
        if not enrollment:
            return None
        status = "active" if enrollment.is_current else "expired"
        return {
            "status": status,
            "valid_till": enrollment.valid_till,
            "payment_type": enrollment.payment_type,
        }

    def get_has_order(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        stats = self.context.get("course_stats")
        if stats:
            return obj.pk in stats["ordered"]

        return obj.pk in course_selectors.ordered_course_ids(request.user, [obj.pk])

    def get_users_count(self, obj) -> int:
        batched = self._stats("enrollment_counts", obj, 0)
        if batched is not None:
            return batched
        return obj.enrollments.count()


class CourseDetailSerializer(CourseListSerializer):
    course_details = serializers.SerializerMethodField()
    prices = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    def get_prices(self, obj) -> list:
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

    def get_course_details(self, obj) -> dict | None:
        return {
            "description": obj.description,
            "features": obj.features,
            "video": obj.video,
            "pdf_link": obj.pdf_link,
        }

    def get_sections(self, obj) -> list:
        children, contents = build_section_tree(obj)
        context = {**self.context, "section_children": children, "section_contents": contents}
        # `children[None]` is the top level: sections with no parent.
        return SectionSerializer(children[None], many=True, context=context).data


class AdminCourseSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)
    categories = serializers.PrimaryKeyRelatedField(many=True, queryset=CourseCategory.objects.all(), required=False)

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
        read_only_fields = ["id"]


class AdminSectionSerializer(serializers.ModelSerializer):
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    section_id = serializers.PrimaryKeyRelatedField(
        source="section", queryset=Section.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Section
        fields = ["id", "course_id", "section_id", "title", "slug", "order", "active"]
        read_only_fields = ["id"]


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

    def get_pivot(self, obj) -> dict | None:
        return {
            "course_id": obj.course_id,
            "user_id": obj.user_id,
            "valid_till": obj.valid_till,
            "payment_type": obj.payment_type,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }


class CourseMaterialSerializer(serializers.ModelSerializer):
    file = MediaField(required=False)
    course_id = serializers.PrimaryKeyRelatedField(
        source="course", queryset=Course.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CourseMaterial
        fields = ["id", "title", "type", "course_id", "file", "created_at"]
        read_only_fields = ["id", "created_at"]


class CourseProgressSerializer(serializers.Serializer):
    """A student's progress through a course.

    Key order is contract: the client destructures this payload.
    """

    completed_content_ids = serializers.ListField(child=serializers.IntegerField())
    completed = serializers.IntegerField()
    total = serializers.IntegerField()
    percent = serializers.IntegerField()


class ContentCompletionRequestSerializer(serializers.Serializer):
    content_id = serializers.IntegerField()


class AdminEnrollmentRequestSerializer(serializers.Serializer):
    """Documents the body the enrolment endpoints accept.

    Used for the OpenAPI schema only, not for validation. The handlers keep
    their own checks because their error messages are contract -- the admin
    panel renders them verbatim -- and because a course may be addressed by
    either `slugOrId` or `course_id`, which is awkward to express as a
    validated field pair without changing those messages.
    """

    #: The course, addressed by numeric id or by slug.
    slugOrId = serializers.CharField(required=False)
    #: Accepted as an alias for `slugOrId`.
    course_id = serializers.CharField(required=False)
    user_id = serializers.IntegerField(required=False)
    #: Attach only. The validity period and payment type are derived from it.
    price_id = serializers.IntegerField(required=False)
    #: Amend only.
    valid_till = serializers.DateTimeField(required=False, allow_null=True)
    payment_type = serializers.CharField(required=False)
