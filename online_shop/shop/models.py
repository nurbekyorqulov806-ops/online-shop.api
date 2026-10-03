from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F
from django.utils.text import slugify


def unique_slug(instance, source):
    """Nomdan takrorlanmas slug yasaydi: iphone-15, iphone-15-2, ..."""
    base = slugify(source)[:60] or instance.__class__.__name__.lower()
    slug = base
    i = 2
    model = instance.__class__
    while model.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True, editable=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, related_name="products", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True, blank=True, editable=False)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to="products/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Review(models.Model):
    product = models.ForeignKey(Product, related_name="reviews", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="reviews", on_delete=models.CASCADE
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = ("product", "user")

    def __str__(self):
        return f"{self.user} -> {self.product} ({self.rating})"


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="cart", on_delete=models.CASCADE
    )
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_price(self):
        return sum(
            (item.subtotal for item in self.items.select_related("product")),
            Decimal("0"),
        )

    def __str__(self):
        return f"Savat: {self.user}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("cart", "product")
        ordering = ["id"]

    @property
    def subtotal(self):
        return self.product.price * self.quantity

    def __str__(self):
        return f"{self.product} x {self.quantity}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        CONFIRMED = "confirmed", "Tasdiqlandi"
        SHIPPED = "shipped", "Yo'lda"
        DELIVERED = "delivered", "Yetkazildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    # Qaysi holatdan qaysi holatga o'tish mumkin
    TRANSITIONS = {
        "pending": ["confirmed", "cancelled"],
        "confirmed": ["shipped", "cancelled"],
        "shipped": ["delivered"],
        "delivered": [],
        "cancelled": [],
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=13)
    address = models.CharField(max_length=255)
    total_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def can_transition(self, new_status):
        return new_status in self.TRANSITIONS.get(self.status, [])

    def restore_stock(self):
        """Bekor qilinganda mahsulotlarni omborga qaytaradi."""
        for item in self.items.all():
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(
                    stock=F("stock") + item.quantity
                )

    def __str__(self):
        return f"Buyurtma #{self.pk} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=200)  # mahsulot o'chsa ham qoladi
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
