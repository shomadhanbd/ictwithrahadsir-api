import json

from rest_framework import serializers

from apps.billing import services, sslcommerz
from apps.billing.models import Order, Payment, Product, ProductCoupon
from apps.courses.models import Coupon, Course, CoursePrice


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
    product_id = serializers.PrimaryKeyRelatedField(source="product", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user_id",
            "course_id",
            "price_id",
            "product_id",
            "item_title",
            "price_title",
            "coupon_code",
            "coupon_discount",
            "amount",
            "total",
            "status",
            "created_at",
        ]
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


class AdminOrderSerializer(OrderSerializer):
    user = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = [*OrderSerializer.Meta.fields, "user"]

    def get_user(self, order) -> dict:
        return {"id": order.user.id, "name": order.user.name, "phone": order.user.phone}


# ---------------------------------------------------------------------------
# Request serializers
#
# These exist so the views stop reaching into `request.data` directly. Each
# one resolves the raw ids it is given into real objects, so a handler
# receives model instances and never has to ask whether they exist.
# ---------------------------------------------------------------------------


class OrderCreateRequestSerializer(serializers.Serializer):
    """One course at one of its prices, or one product; optionally a coupon.

    Resolves the ids into objects, so the result can be passed straight to
    `services.quote` / `services.create_order`.
    """

    course_id = serializers.IntegerField(required=False)
    price_id = serializers.IntegerField(required=False)
    product_id = serializers.IntegerField(required=False)
    coupon_code = serializers.CharField(required=False, allow_blank=True, max_length=50, default='')

    def validate(self, attrs):
        code = attrs.get('coupon_code', '')
        if attrs.get('product_id') is not None:
            if attrs.get('course_id') is not None:
                raise serializers.ValidationError({'product_id': ['Order a course or a product, not both.']})
            product = Product.objects.filter(pk=attrs['product_id'], active=True).first()
            if product is None:
                raise serializers.ValidationError({'product_id': ['This product is not available.']})
            return {'product': product, 'coupon_code': code}
        return {**self._validate_course(attrs), 'coupon_code': code}

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


class OrderQuoteSerializer(serializers.Serializer):
    """What an order would cost, before it is placed."""

    item_title = serializers.CharField()
    price_title = serializers.CharField(allow_blank=True)
    base = serializers.DecimalField(max_digits=10, decimal_places=2)
    coupon_code = serializers.CharField(allow_blank=True)
    coupon_discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class OrderPayResponseSerializer(serializers.Serializer):
    """Where to send the student. `gateway_url` is null when there was
    nothing to pay and the order is already complete."""

    gateway_url = serializers.URLField(allow_null=True)
    order = OrderSerializer()


class SslCommerzCallbackSerializer(serializers.Serializer):
    """The fields read from an SSLCommerz callback. Everything else it posts is
    ignored: the payment is settled from the validation API, not from this."""

    tran_id = serializers.CharField()
    val_id = serializers.CharField(required=False, allow_blank=True, default='')
    status = serializers.CharField(required=False, allow_blank=True, default='')


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductCourseSerializer(serializers.ModelSerializer):
    """A course a product unlocks. `is_online` tells live from recorded."""

    class Meta:
        model = Course
        fields = ["id", "title", "slug", "is_online"]


ACCESS_FIELDS = ["access_days", "access_ends_on"]


class ProductSerializer(serializers.ModelSerializer):
    courses = ProductCourseSerializer(many=True, read_only=True)
    price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "thumbnail",
            "courses",
            "amount",
            "discount",
            "discount_till",
            "price",
            *ACCESS_FIELDS,
        ]

    def get_price(self, product) -> str:
        """What it costs right now, after any live discount."""
        return f'{services.price_after_discount(product):.2f}'


class AdminProductSerializer(serializers.ModelSerializer):
    courses = ProductCourseSerializer(many=True, read_only=True)
    course_ids = serializers.PrimaryKeyRelatedField(
        source="courses", queryset=Course.objects.all(), many=True, write_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "thumbnail",
            "courses",
            "course_ids",
            "amount",
            "discount",
            "discount_till",
            *ACCESS_FIELDS,
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"slug": {"required": False}}

    def validate_course_ids(self, courses):
        if not courses:
            raise serializers.ValidationError('A product has to unlock at least one course.')
        return courses

    def validate_amount(self, value):
        if value > sslcommerz.MAX_AMOUNT:
            raise serializers.ValidationError(f'SSLCommerz accepts at most {sslcommerz.MAX_AMOUNT:g} BDT.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        def after(field):
            return attrs.get(field, getattr(self.instance, field, None))

        amount, discount = after('amount'), after('discount')
        if amount is not None and discount and discount > amount:
            raise serializers.ValidationError({'discount': ['The discount cannot exceed the price.']})
        if after('access_days') and after('access_ends_on'):
            raise serializers.ValidationError(
                {'access_ends_on': ['Give a number of days or an end date, not both. Leave both blank for lifetime.']}
            )
        return attrs


class ProductCouponSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(source="product", queryset=Product.objects.all())

    class Meta:
        model = ProductCoupon
        fields = [
            "id",
            "product_id",
            "code",
            "discount_type",
            "discount",
            "valid_till",
            "usage_limit",
            "active",
            "created_at",
        ]
        read_only_fields = ["created_at"]
        # Checked in `validate`, on the upper-cased code.
        validators = []

    def validate_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        product = attrs.get('product', getattr(self.instance, 'product', None))
        code = attrs.get('code', getattr(self.instance, 'code', ''))
        clash = ProductCoupon.objects.filter(product=product, code__iexact=code)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({'code': ['This product already has that coupon code.']})

        kind = attrs.get('discount_type', getattr(self.instance, 'discount_type', Coupon.DiscountType.PERCENT))
        discount = attrs.get('discount', getattr(self.instance, 'discount', None))
        if discount is not None and discount <= 0:
            raise serializers.ValidationError({'discount': ['The discount must be more than zero.']})
        if kind == Coupon.DiscountType.PERCENT and discount is not None and discount > 100:
            raise serializers.ValidationError({'discount': ['A percentage discount cannot exceed 100.']})
        return attrs


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
