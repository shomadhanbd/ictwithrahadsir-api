import json

from rest_framework import serializers

from apps.billing.models import Order, Payment
from apps.courses.models import Course, CoursePrice


class DetailsJsonStringField(serializers.Field):
    """Serialises `Payment.details` as a JSON *string*, not an object.

    Both payment payloads have always sent it this way and the frontends
    parse it as a string, so it is contract. Defined once here because the
    same three lines were previously repeated on two serializers.

    `source="*"` because it reads the whole `Payment`, not one attribute.
    """

    def __init__(self, **kwargs):
        kwargs['read_only'] = True
        kwargs.setdefault('source', '*')
        super().__init__(**kwargs)

    #: A JSON document, sent as a string. Declared so the generated schema
    #: says so rather than defaulting to an untyped "string".
    _spectacular_annotation = {'field': {'type': 'string', 'format': 'json'}}

    def to_representation(self, payment):
        return json.dumps(payment.details)


class OrderSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(source="user", read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(source="course", read_only=True)
    price_id = serializers.PrimaryKeyRelatedField(source="price", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user_id",
            "course_id",
            "price_id",
            "item_title",
            "price_title",
            "amount",
            "total",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.PrimaryKeyRelatedField(source="order", read_only=True)
    details = DetailsJsonStringField()

    class Meta:
        model = Payment
        fields = ["id", "order_id", "amount", "transaction_id", "details", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class AdminPaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.PrimaryKeyRelatedField(source="order", read_only=True)
    order = OrderSerializer(read_only=True)
    user = serializers.SerializerMethodField()
    details = DetailsJsonStringField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "order_id",
            "order",
            "user",
            "amount",
            "transaction_id",
            "details",
            "status",
            "created_at",
        ]

    def get_user(self, obj) -> dict | None:
        user = obj.order.user
        return {"id": user.id, "name": user.name, "phone": user.phone}


# ---------------------------------------------------------------------------
# Request serializers
#
# These exist so the views stop reaching into `request.data` directly. Each
# one resolves the raw ids it is given into real objects, so a handler
# receives model instances and never has to ask whether they exist.
# ---------------------------------------------------------------------------


class OrderCreateRequestSerializer(serializers.Serializer):
    """Places an order for a course at one of its prices.

    It used to place product orders too, selected by a `product_id` in the
    body. The `store` app those pointed at has been removed.
    """

    course_id = serializers.IntegerField(required=False)
    price_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        return self._validate_course(attrs)

    def _validate_course(self, attrs):
        course_id = attrs.get('course_id')
        course = Course.objects.filter(pk=course_id, active=True).first()
        price = (
            CoursePrice.objects.filter(
                pk=attrs.get('price_id'),
                priceable_type=CoursePrice.PRICEABLE_COURSE,
                priceable_id=course_id,
            ).first()
            if course
            else None
        )
        if not course or not price:
            raise serializers.ValidationError({'price_id': ['Invalid course/price selection.']})
        return {'course': course, 'price': price}


class PaymentSubmitRequestSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    transaction_id = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True, default='')
    details = serializers.JSONField(required=False, default=dict)

    def validate_details(self, value):
        # The client posts this as a JSON string in multipart submissions and
        # as a real object in JSON ones.
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                raise serializers.ValidationError('Must be valid JSON.')
        return value or {}


class FreeEnrollmentRequestSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()


class PaymentStatusUpdateRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=Payment.Status.choices, error_messages={'invalid_choice': 'Invalid status.'}
    )
    confirm_amount_mismatch = serializers.BooleanField(required=False, default=False)


class FreeEnrollmentResponseSerializer(serializers.Serializer):
    """Confirms the claim and echoes back which course it was for."""

    ok = serializers.BooleanField()
    course_id = serializers.IntegerField()


class OrderCreateResponseSerializer(serializers.Serializer):
    """`{id, order}` -- the new order's id alongside the order itself.

    The redundant top-level `id` is what the checkout flow reads to build its
    redirect, so it stays.
    """

    id = serializers.IntegerField()
    order = OrderSerializer()
