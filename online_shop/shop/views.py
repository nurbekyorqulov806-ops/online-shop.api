import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Avg, Count, F, Sum
from django.shortcuts import get_object_or_404
from rest_framework import filters, generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import (
    IsAdminUser, IsAuthenticated, IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from .emails import send_email, send_order_confirmation, send_order_status_update
from .models import Cart, CartItem, Category, Order, OrderItem, Product, Review
from .permissions import IsAdminOrReadOnly, IsOwnerOrAdmin
from .serializers import (
    CartItemCreateSerializer, CartItemUpdateSerializer, CartSerializer,
    CategorySerializer, CheckoutSerializer, OrderSerializer,
    OrderStatusSerializer, ProductSerializer, ReviewSerializer,
)

User = get_user_model()
NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")


# ======================= KATEGORIYA =======================
class CategoryViewSet(viewsets.ModelViewSet):
    """
    GET    /api/categories/        - ro'yxat (hamma)
    GET    /api/categories/<id>/   - bitta kategoriya (hamma)
    POST   /api/categories/        - yaratish (admin)
    PUT/PATCH/DELETE /<id>/        - o'zgartirish / o'chirish (admin)
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]


# ======================= MAHSULOT =======================
class ProductViewSet(viewsets.ModelViewSet):
    """
    GET /api/products/?search=&category=<id|slug>&min_price=&max_price=
                       &in_stock=true&ordering=price|-price|-created_at|name&page=
    Yaratish / o'zgartirish / o'chirish faqat admin uchun.
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "category__name"]
    ordering_fields = ["price", "created_at", "name"]

    def get_queryset(self):
        qs = Product.objects.select_related("category").annotate(
            avg_rating_value=Avg("reviews__rating"),
            reviews_count_value=Count("reviews"),
        )
        params = self.request.query_params

        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)

        category = params.get("category")
        if category:
            if category.isdigit():
                qs = qs.filter(category_id=int(category))
            else:
                qs = qs.filter(category__slug=category)

        for key, lookup in (("min_price", "price__gte"), ("max_price", "price__lte")):
            value = params.get(key)
            if value:
                if not NUMBER_RE.match(value):
                    raise ValidationError({key: "Son kiriting."})
                qs = qs.filter(**{lookup: Decimal(value)})

        if params.get("in_stock", "").lower() in ("1", "true", "yes"):
            qs = qs.filter(stock__gt=0)

        return qs

    @action(
        detail=True, methods=["get", "post"], url_path="reviews",
        permission_classes=[IsAuthenticatedOrReadOnly],
    )
    def reviews(self, request, pk=None):
        """GET - sharhlar ro'yxati, POST - sharh qoldirish (login kerak)."""
        product = self.get_object()

        if request.method == "GET":
            page = self.paginate_queryset(product.reviews.select_related("user"))
            return self.get_paginated_response(
                ReviewSerializer(page, many=True).data
            )

        if product.reviews.filter(user=request.user).exists():
            raise ValidationError("Siz bu mahsulotga allaqachon sharh qoldirgansiz.")
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, product=product)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Sharhni ko'rish (hamma), o'zgartirish/o'chirish (egasi yoki admin)."""

    queryset = Review.objects.select_related("user")
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]


# ======================= SAVAT =======================
def get_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def cart_response(cart, request, status_code=status.HTTP_200_OK):
    return Response(CartSerializer(cart, context={"request": request}).data, status=status_code)


class CartView(APIView):
    """GET - savatni ko'rish, DELETE - savatni tozalash."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return cart_response(get_cart(request.user), request)

    def delete(self, request):
        cart = get_cart(request.user)
        cart.items.all().delete()
        return cart_response(cart, request)


class CartItemCreateView(APIView):
    """POST - savatga mahsulot qo'shish: {"product": 1, "quantity": 2}"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]

        cart = get_cart(request.user)
        item = cart.items.filter(product=product).first()
        new_quantity = (item.quantity if item else 0) + quantity
        if new_quantity > product.stock:
            raise ValidationError({"quantity": f"Omborda faqat {product.stock} dona bor."})

        if item:
            item.quantity = new_quantity
            item.save()
        else:
            CartItem.objects.create(cart=cart, product=product, quantity=new_quantity)
        return cart_response(cart, request, status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    """PATCH - miqdorni o'zgartirish, DELETE - savatdan o'chirish."""

    permission_classes = [IsAuthenticated]

    def get_item(self, request, pk):
        return get_object_or_404(
            CartItem.objects.select_related("product", "cart"),
            pk=pk, cart__user=request.user,
        )

    def patch(self, request, pk):
        item = self.get_item(request, pk)
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]
        if quantity > item.product.stock:
            raise ValidationError({"quantity": f"Omborda faqat {item.product.stock} dona bor."})
        item.quantity = quantity
        item.save()
        return cart_response(item.cart, request)

    def delete(self, request, pk):
        item = self.get_item(request, pk)
        cart = item.cart
        item.delete()
        return cart_response(cart, request)


# ======================= BUYURTMA =======================
class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET   /api/orders/                 - o'z buyurtmalarim (admin: hammasi, ?status=)
    GET   /api/orders/<id>/            - bitta buyurtma
    POST  /api/orders/                 - savatdan buyurtma berish (checkout)
    POST  /api/orders/<id>/cancel/     - bekor qilish
    PATCH /api/orders/<id>/status/     - holatni o'zgartirish (admin)
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "total_price"]

    def get_queryset(self):
        qs = Order.objects.select_related("user").prefetch_related("items")
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def create(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = get_cart(request.user)

        with transaction.atomic():
            items = list(cart.items.select_related("product"))
            if not items:
                raise ValidationError({"detail": "Savat bo'sh."})

            products = {
                p.pk: p
                for p in Product.objects.select_for_update().filter(
                    pk__in=[i.product_id for i in items]
                )
            }
            errors = []
            for item in items:
                product = products[item.product_id]
                if not product.is_active:
                    errors.append(f"'{product.name}' sotuvda yo'q.")
                elif item.quantity > product.stock:
                    errors.append(
                        f"'{product.name}' uchun omborda faqat {product.stock} dona bor."
                    )
            if errors:
                raise ValidationError({"detail": errors})

            order = Order.objects.create(user=request.user, **serializer.validated_data)
            total = Decimal("0")
            for item in items:
                product = products[item.product_id]
                OrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    price=product.price, quantity=item.quantity,
                )
                Product.objects.filter(pk=product.pk).update(stock=F("stock") - item.quantity)
                total += product.price * item.quantity
            order.total_price = total
            order.save(update_fields=["total_price", "updated_at"])
            cart.items.all().delete()

        email_sent = send_order_confirmation(order)
        data = dict(OrderSerializer(order).data)
        data["email_sent"] = email_sent
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if not order.can_transition("cancelled"):
            raise ValidationError({"detail": "Bu buyurtmani bekor qilib bo'lmaydi."})
        with transaction.atomic():
            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])
            order.restore_stock()
        send_order_status_update(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["patch"], url_path="status", permission_classes=[IsAdminUser])
    def set_status(self, request, pk=None):
        order = self.get_object()
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        if not order.can_transition(new_status):
            raise ValidationError(
                {"status": f"'{order.status}' holatidan '{new_status}' holatiga o'tib bo'lmaydi."}
            )
        with transaction.atomic():
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])
            if new_status == Order.Status.CANCELLED:
                order.restore_stock()
        send_order_status_update(order)
        return Response(OrderSerializer(order).data)


# ======================= ADMIN: STATISTIKA va EMAIL =======================
class StatsView(APIView):
    """GET /api/stats/ - admin uchun umumiy statistika."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        valid_orders = Order.objects.exclude(status=Order.Status.CANCELLED)
        revenue = valid_orders.aggregate(s=Sum("total_price"))["s"] or 0
        top = (
            OrderItem.objects.exclude(order__status=Order.Status.CANCELLED)
            .values("product_name")
            .annotate(sold=Sum("quantity"))
            .order_by("-sold")[:5]
        )
        return Response({
            "users": User.objects.count(),
            "products": Product.objects.count(),
            "orders": Order.objects.count(),
            "orders_by_status": {
                value: Order.objects.filter(status=value).count()
                for value, _ in Order.Status.choices
            },
            "revenue": revenue,
            "top_products": list(top),
        })


class SendEmailView(APIView):
    """POST /api/send-email/ - istalgan manzilga xat yuborish (faqat admin)."""

    permission_classes = [IsAdminUser]

    def post(self, request):
        to = request.data.get("to")
        subject = request.data.get("subject")
        message = request.data.get("message")
        if not (to and subject and message):
            raise ValidationError("to, subject va message majburiy.")
        if send_email(subject, message, [to]):
            return Response({"detail": "Email yuborildi."})
        return Response(
            {"detail": "Email yuborishda xatolik yuz berdi."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
