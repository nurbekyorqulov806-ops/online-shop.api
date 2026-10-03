from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CartItemCreateView, CartItemDetailView, CartView, CategoryViewSet,
    OrderViewSet, ProductViewSet, ReviewDetailView, SendEmailView, StatsView,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemCreateView.as_view(), name="cart-item-add"),
    path("cart/items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("reviews/<int:pk>/", ReviewDetailView.as_view(), name="review-detail"),
    path("stats/", StatsView.as_view(), name="stats"),
    path("send-email/", SendEmailView.as_view(), name="send-email"),
] + router.urls
