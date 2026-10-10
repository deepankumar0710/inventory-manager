from django.db import models

LOW_STOCK_LIMIT = 5


class Product(models.Model):
    product_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    stock = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def status(self):
        if self.stock == 0:
            return "out"
        if self.stock <= LOW_STOCK_LIMIT:
            return "low"
        return "ok"


class Sale(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    date_sold = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"