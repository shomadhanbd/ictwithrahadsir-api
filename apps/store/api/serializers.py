from rest_framework import serializers

from apps.core.api.fields import MediaField
from apps.courses.models import CourseCategory
from apps.store.models import CartItem, Product


class ProductSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="product", required=False)
    categories = serializers.PrimaryKeyRelatedField(many=True, queryset=CourseCategory.objects.all(), required=False)

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


class CartAddRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(
        error_messages={'required': 'Product not found.', 'invalid': 'Product not found.'}
    )


class CartQuantityRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=['increment', 'decrement'],
        error_messages={
            'invalid_choice': 'Must be `increment` or `decrement`.',
            'required': 'Must be `increment` or `decrement`.',
        },
    )
