from rest_framework import serializers

from apps.core.fields import MediaField
from apps.courses.models import CourseCategory

from .models import CartItem, Order, Payment, Product


class ProductSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="product", required=False)
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=CourseCategory.objects.all(), required=False
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "discount",
            "discount_till",
            "coupon",
            "coupon_discount",
            "coupon_discount_type",
            "coupon_valid_till",
            "featured",
            "stock",
            "order",
            "sku",
            "barcode",
            "active",
            "is_book",
            "categories",
            "image",
        ]
        read_only_fields = ["id", "slug"]


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity"]
        read_only_fields = ["id"]


class OrderSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(source="user", read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(source="course", read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(source="product", read_only=True)
    price_id = serializers.PrimaryKeyRelatedField(source="price", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user_id",
            "course_id",
            "product_id",
            "price_id",
            "quantity",
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
    details = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["id", "order_id", "amount", "transaction_id", "details", "status", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_details(self, obj):
        import json

        return json.dumps(obj.details)


class AdminPaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.PrimaryKeyRelatedField(source="order", read_only=True)
    order = OrderSerializer(read_only=True)
    user = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()

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

    def get_user(self, obj):
        user = obj.order.user
        return {"id": user.id, "name": user.name, "phone": user.phone}

    def get_details(self, obj):
        import json

        return json.dumps(obj.details)
