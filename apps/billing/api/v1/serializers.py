from rest_framework import serializers

from apps.core.api.fields import MediaField
from apps.courses.models import CourseCategory

from apps.billing.models import Order, Payment


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
