from datetime import datetime

from django.utils import timezone

from rest_framework import serializers

from apps.billing.models import Payment, Product
from apps.billing.selectors import access_until
from apps.billing.services.sslcommerz import MIN_AMOUNT
from apps.courses.models import Course
from apps.identity.models import User

MAX_AMOUNT = 500000


def _user_summary(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "name": user.name, "phone": user.phone}


def _chargeable(value):
    if value > MAX_AMOUNT:
        raise serializers.ValidationError(f"SSLCommerz accepts at most {MAX_AMOUNT} BDT.")
    if 0 < value < MIN_AMOUNT:
        raise serializers.ValidationError(f"SSLCommerz accepts at least {MIN_AMOUNT} BDT; 0 makes it free.")
    return value


class ProductCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "title", "slug", "is_online", "status"]


class ProductSerializer(serializers.ModelSerializer):
    courses = ProductCourseSerializer(many=True, read_only=True)
    price = serializers.IntegerField(source="current_price", read_only=True)
    base_price = serializers.SerializerMethodField()
    discount_ends_at = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "product_id",
            "title",
            "description",
            "courses",
            "price",
            "base_price",
            "discount_ends_at",
            "access_days",
            "access_ends_on",
        ]
        read_only_fields = fields

    def get_base_price(self, product) -> int:
        return product.base_price if product.discount_active else product.current_price

    def get_discount_ends_at(self, product) -> datetime | None:
        return product.discount_ends_at if product.discount_active else None


class AdminProductSerializer(serializers.ModelSerializer):
    courses = ProductCourseSerializer(many=True, read_only=True)
    course_ids = serializers.PrimaryKeyRelatedField(source="courses", queryset=Course.objects.all(), many=True)
    payment_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "product_id",
            "title",
            "description",
            "courses",
            "course_ids",
            "price",
            "base_price",
            "discount_ends_at",
            "access_days",
            "access_ends_on",
            "is_active",
            "payment_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"product_id": {"required": False}}

    def get_payment_count(self, product) -> int:
        annotated = getattr(product, "payment_count", None)
        if annotated is not None:
            return annotated
        return product.payments.filter(status=Payment.Status.VALID).count()

    def validate_course_ids(self, courses):
        if not courses:
            raise serializers.ValidationError("A product has to unlock at least one course.")
        return courses

    def validate_price(self, value):
        return _chargeable(value)

    def validate_base_price(self, value):
        # Charged once a discount ends, so it must be payable too.
        return _chargeable(value)

    def validate(self, attrs):
        def after(field):
            return attrs.get(field, getattr(self.instance, field, None))

        price, base_price = after("price"), after("base_price")
        if price is not None and base_price is not None and base_price < price:
            raise serializers.ValidationError({"base_price": ["The base price cannot be below the price."]})
        if after("discount_ends_at") and base_price is not None and price is not None and base_price <= price:
            raise serializers.ValidationError(
                {"discount_ends_at": ["A discount end needs an original price higher than the price."]}
            )
        if after("access_days") and after("access_ends_on"):
            raise serializers.ValidationError(
                {"access_ends_on": ["Give a number of days or an end date, not both. Leave both blank for lifetime."]}
            )
        return attrs


class PaymentInitiateRequestSerializer(serializers.Serializer):
    product_id = serializers.CharField(max_length=280)


class PaymentInitiateResponseSerializer(serializers.Serializer):
    """`gateway_page_url` is null when there was nothing to pay."""

    transaction_id = serializers.CharField()
    gateway_page_url = serializers.URLField(allow_null=True)


class PaymentCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "slug", "title"]


class PaymentSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    product_id = serializers.SlugRelatedField(source="product", slug_field="product_id", read_only=True)
    courses = PaymentCourseSerializer(source="product.courses", many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "transaction_id",
            "title",
            "product_id",
            "amount",
            "status",
            "transaction_date",
            "created_at",
            "courses",
        ]
        read_only_fields = fields


class AdminPaymentSerializer(PaymentSerializer):
    user = serializers.SerializerMethodField()
    recorded_by = serializers.SerializerMethodField()

    class Meta(PaymentSerializer.Meta):
        fields = [
            "id",
            *PaymentSerializer.Meta.fields,
            "user",
            "method",
            "recorded_by",
            "note",
            "card_type",
            "card_issuer_country",
        ]
        read_only_fields = fields

    def get_user(self, payment) -> dict | None:
        return _user_summary(payment.user)

    def get_recorded_by(self, payment) -> dict | None:
        return _user_summary(payment.recorded_by)


class CashSaleRequestSerializer(serializers.Serializer):
    """A sale taken at the centre: who paid, for which package of which course, how much, and until when."""

    user_id = serializers.PrimaryKeyRelatedField(source="user", queryset=User.objects.all())
    course_id = serializers.PrimaryKeyRelatedField(source="course", queryset=Course.objects.all())
    product_id = serializers.PrimaryKeyRelatedField(source="product", queryset=Product.objects.all())
    amount = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    valid_till = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_valid_till(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Must be in the future.")
        return value

    def validate(self, attrs):
        if not attrs["product"].courses.filter(pk=attrs["course"].pk).exists():
            raise serializers.ValidationError({"product_id": "This package does not include the course."})
        if not attrs.get("valid_till"):
            ends = access_until(attrs["product"])
            if ends is not None and ends <= timezone.now():
                raise serializers.ValidationError(
                    {"valid_till": "This package's access has already ended. Give the date access should run until."}
                )
        return attrs
