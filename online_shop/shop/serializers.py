from django.db.models import Avg
from rest_framework import serializers

from accounts.validators import validate_phone as validate_uz_phone

from .models import Cart, CartItem, Category, Order, OrderItem, Product, Review


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "category", "category_name", "name", "slug", "description",
            "price", "stock", "image", "is_active",
            "avg_rating", "reviews_count", "created_at",
        ]

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_avg_rating(self, obj):
        if hasattr(obj, "avg_rating_value"):
            value = obj.avg_rating_value
        else:
            value = obj.reviews.aggregate(v=Avg("rating"))["v"]
        return round(value, 1) if value is not None else None

    def get_reviews_count(self, obj):
        if hasattr(obj, "reviews_count_value"):
            return obj.reviews_count_value
        return obj.reviews.count()


class ProductBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "slug", "price", "stock", "image"]


class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)
    product = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "user", "rating", "comment", "created_at"]


# ---------------- Savat ----------------
class CartItemSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity", "subtotal"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    total_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "items_count", "total_price"]

    def get_items_count(self, obj):
        return sum(item.quantity for item in obj.items.all())


class CartItemCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


# ---------------- Buyurtma ----------------
class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "price", "quantity", "subtotal"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.CharField(source="user.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "user", "status", "status_display", "customer_name", "phone",
            "address", "total_price", "items", "created_at", "updated_at",
        ]
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=150)
    phone = serializers.CharField()
    address = serializers.CharField(max_length=255)

    def validate_phone(self, value):
        return validate_uz_phone(value)


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
