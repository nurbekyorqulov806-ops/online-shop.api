from django.core.management.base import BaseCommand

from shop.models import Category, Product


class Command(BaseCommand):
    help = "Test uchun kategoriya va mahsulotlar yaratadi"

    def handle(self, *args, **options):
        data = {
            "Telefonlar": [("iPhone 15", 12000000, 10), ("Samsung S24", 10000000, 8)],
            "Noutbuklar": [("MacBook Air", 15000000, 5), ("Lenovo IdeaPad", 7000000, 12)],
            "Aksessuarlar": [("AirPods", 2500000, 20), ("Telefon g'ilofi", 80000, 50)],
        }
        for cat_name, products in data.items():
            category, _ = Category.objects.get_or_create(name=cat_name)
            for name, price, stock in products:
                Product.objects.get_or_create(
                    name=name,
                    defaults={
                        "category": category, "price": price, "stock": stock,
                        "description": f"{name} - sifatli mahsulot",
                    },
                )
        self.stdout.write(self.style.SUCCESS("Test ma'lumotlar yaratildi."))
