from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import LOW_STOCK_LIMIT, Product, Sale

LOOKBACK_DAYS = 7   # how many days of sales we look at
WARNING_DAYS = 7    # warn when the stock will last this many days or fewer


class NotEnoughStock(Exception):
    """Raised when someone tries to sell more than we have."""


def sell_product(product, quantity):
    with transaction.atomic():
        # Read the product again, because the stock may have
        # changed since the form was opened.
        locked = Product.objects.select_for_update().get(pk=product.pk)

        if quantity > locked.stock:
            raise NotEnoughStock(f"Only {locked.stock} of {locked.name} left.")

        locked.stock -= quantity
        locked.save()

        return Sale.objects.create(
            product=locked,
            quantity=quantity,
            total_price=locked.price * quantity,
        )


def days_of_stock_left(stock, units_sold, days=LOOKBACK_DAYS):
    """How many days will the stock last? None means 'nothing sold lately'."""
    if units_sold <= 0:
        return None
    per_day = units_sold / days
    return stock / per_day


def restock_alerts():
    """Return the products that need attention, most urgent first."""
    since = timezone.now() - timedelta(days=LOOKBACK_DAYS)
    products = Product.objects.annotate(
        recent_units=Sum("sale__quantity", filter=Q(sale__date_sold__gte=since))
    )

    alerts = []
    for product in products:
        recent = product.recent_units or 0
        days_left = days_of_stock_left(product.stock, recent)

        if product.stock == 0:
            rank, label = 0, "Out of stock"
        elif product.stock <= LOW_STOCK_LIMIT:
            rank, label = 1, "Low stock"
        elif days_left is not None and days_left <= WARNING_DAYS:
            rank, label = 2, "Selling fast"
        else:
            continue  # this product is fine

        alerts.append(
            {
                "product": product,
                "recent": recent,
                "days_left": days_left,
                "label": label,
                "rank": rank,
            }
        )

    alerts.sort(
        key=lambda a: (a["rank"], a["days_left"] if a["days_left"] is not None else 9999)
    )
    return alerts