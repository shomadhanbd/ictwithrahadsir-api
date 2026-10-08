from rest_framework import serializers

from apps.academic.models import ClassLevel, Group
from apps.core.api.serializers.fields import MediaField, PhoneField
from apps.courses.models import Course
from apps.materials.models import BookOrder, DeliveryRate, MaterialCategory, MaterialItem, MaterialTopic
from apps.materials.validators import validate_item, validate_topic_access


class AudienceSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()


class LibraryCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialCategory
        fields = ["id", "name", "icon"]


class LibraryTopicSerializer(serializers.ModelSerializer):
    """`context["opens"]` decides `locked`; a locked topic leaves out its items' links."""

    category = LibraryCategorySerializer(read_only=True)
    class_level = AudienceSerializer(read_only=True)
    group = AudienceSerializer(read_only=True)
    locked = serializers.SerializerMethodField()
    unlock_courses = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    class Meta:
        model = MaterialTopic
        fields = [
            "id",
            "title",
            "description",
            "cover",
            "category",
            "class_level",
            "group",
            "access",
            "locked",
            "unlock_courses",
            "items",
        ]

    def get_locked(self, topic) -> bool:
        return not self.context["opens"](topic)

    def get_unlock_courses(self, topic) -> list:
        if topic.access == MaterialTopic.Access.FREE:
            return []
        return [{"slug": course.slug, "title": course.title} for course in topic.courses.all()]

    def get_items(self, topic) -> list:
        locked = self.get_locked(topic)
        return [
            {
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "description": item.description,
                "url": None if locked else item.url,
                "image": item.image or None,
                "preview_url": None if locked else (item.preview_url or None),
                "price": item.price,
            }
            for item in topic.items.all()
        ]


class DeliveryRateSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_zone_display", read_only=True)

    class Meta:
        model = DeliveryRate
        fields = ["zone", "label", "charge"]
        read_only_fields = ["zone"]


class BookOrderRequestSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    name = serializers.CharField(max_length=100)
    phone = PhoneField()
    address = serializers.CharField(max_length=500)
    zone = serializers.ChoiceField(choices=DeliveryRate.Zone.choices)


class AdminCategorySerializer(serializers.ModelSerializer):
    topic_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MaterialCategory
        fields = ["id", "name", "icon", "is_active", "order", "topic_count"]
        read_only_fields = ["id"]


class AdminItemSerializer(serializers.ModelSerializer):
    topic_id = serializers.PrimaryKeyRelatedField(source="topic", queryset=MaterialTopic.objects.all())
    image = MediaField(required=False, null_as="", bare=True)
    url = serializers.URLField(max_length=500, required=False, allow_blank=True)

    class Meta:
        model = MaterialItem
        fields = ["id", "topic_id", "kind", "title", "description", "url", "image", "preview_url", "price", "order"]
        read_only_fields = ["id", "order"]

    def validate(self, attrs):
        def after(field):
            return attrs.get(field, getattr(self.instance, field, None))

        if self.instance is not None and "topic" in attrs and attrs["topic"] != self.instance.topic:
            raise serializers.ValidationError({"topic_id": "An item stays in its topic."})
        validate_item(kind=after("kind"), url=after("url"), price=after("price"))
        return attrs


class AdminTopicSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(source="category", queryset=MaterialCategory.objects.all())
    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all(), required=False, allow_null=True
    )
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.all(), required=False, allow_null=True
    )
    course_ids = serializers.PrimaryKeyRelatedField(
        source="courses", queryset=Course.objects.all(), many=True, required=False
    )
    cover = MediaField(required=False, null_as="", bare=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    courses = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()

    class Meta:
        model = MaterialTopic
        fields = [
            "id",
            "category_id",
            "category_name",
            "title",
            "description",
            "cover",
            "class_level_id",
            "group_id",
            "access",
            "course_ids",
            "courses",
            "is_published",
            "order",
            "counts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_counts(self, topic) -> dict:
        return {kind: getattr(topic, f"{kind}_count", 0) for kind in MaterialItem.Kind.values}

    def get_courses(self, topic) -> list:
        return [{"id": course.id, "title": course.title} for course in topic.courses.all()]

    def validate(self, attrs):
        access = attrs.get("access", getattr(self.instance, "access", MaterialTopic.Access.FREE))
        if "courses" in attrs:
            courses = attrs["courses"]
        else:
            courses = list(self.instance.courses.all()) if self.instance else []
        validate_topic_access(access=access, courses=courses)
        return attrs


class AdminTopicDetailSerializer(AdminTopicSerializer):
    items = AdminItemSerializer(many=True, read_only=True)

    class Meta(AdminTopicSerializer.Meta):
        fields = [*AdminTopicSerializer.Meta.fields, "items"]


class MoveSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=["up", "down"])


class AdminBookOrderSerializer(serializers.ModelSerializer):
    transaction_id = serializers.CharField(source="payment.transaction_id")
    amount = serializers.IntegerField(source="payment.amount")
    paid_at = serializers.SerializerMethodField()
    zone_label = serializers.CharField(source="get_zone_display")
    buyer = serializers.SerializerMethodField()

    class Meta:
        model = BookOrder
        fields = [
            "id",
            "title",
            "name",
            "phone",
            "address",
            "zone",
            "zone_label",
            "book_price",
            "delivery_charge",
            "amount",
            "transaction_id",
            "paid_at",
            "buyer",
        ]
        read_only_fields = fields

    def get_paid_at(self, order):
        return order.payment.transaction_date or order.payment.created_at

    def get_buyer(self, order) -> dict | None:
        user = order.payment.user
        return {"id": user.id, "name": user.name, "phone": user.phone} if user else None
