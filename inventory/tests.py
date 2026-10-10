import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Product, Sale
from .services import NotEnoughStock, days_of_stock_left, restock_alerts, sell_product


def make_product(**kwargs):
    """Create a product for a test. Any value can be changed with kwargs."""
    values = {
        "product_id": "P1",
        "name": "Tea",
        "stock": 10,
        "price": Decimal("20.00"),
    }
    values.update(kwargs)
    return Product.objects.create(**values)


# ---------------------------------------------------------------
# 1. Plain Python tests (no database, so they are very fast)
# ---------------------------------------------------------------
class ProductStatusTests(SimpleTestCase):
    def test_zero_stock_is_out(self):
        self.assertEqual(Product(stock=0).status, "out")

    def test_five_or_less_is_low(self):
        self.assertEqual(Product(stock=5).status, "low")

    def test_six_or_more_is_ok(self):
        self.assertEqual(Product(stock=6).status, "ok")


class DaysOfStockLeftTests(SimpleTestCase):
    def test_normal_case(self):
        # 14 sold in 7 days = 2 per day, so 20 in stock lasts 10 days
        self.assertEqual(days_of_stock_left(20, 14), 10.0)

    def test_nothing_sold_means_unknown(self):
        self.assertIsNone(days_of_stock_left(20, 0))

    def test_no_stock_means_zero_days(self):
        self.assertEqual(days_of_stock_left(0, 5), 0.0)


# ---------------------------------------------------------------
# 2. Selling (database tests)
# ---------------------------------------------------------------
class SellProductTests(TestCase):
    def test_sale_reduces_stock_and_saves_history(self):
        product = make_product(stock=10)

        sale = sell_product(product, 3)

        product.refresh_from_db()
        self.assertEqual(product.stock, 7)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(sale.total_price, Decimal("60.00"))

    def test_not_enough_stock_changes_nothing(self):
        product = make_product(stock=2)

        with self.assertRaises(NotEnoughStock):
            sell_product(product, 5)

        product.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertEqual(Sale.objects.count(), 0)

    def test_can_sell_the_last_unit(self):
        product = make_product(stock=1)

        sell_product(product, 1)

        product.refresh_from_db()
        self.assertEqual(product.stock, 0)

    def test_old_sale_keeps_its_price(self):
        product = make_product(stock=10, price=Decimal("20.00"))
        sale = sell_product(product, 2)

        product.price = Decimal("50.00")
        product.save()

        sale.refresh_from_db()
        self.assertEqual(sale.total_price, Decimal("40.00"))


# ---------------------------------------------------------------
# 3. Restock alerts
# ---------------------------------------------------------------
class RestockAlertTests(TestCase):
    def labels(self):
        return [a["label"] for a in restock_alerts()]

    def test_out_of_stock_is_an_alert(self):
        make_product(stock=0)
        self.assertEqual(self.labels(), ["Out of stock"])

    def test_low_stock_is_an_alert(self):
        make_product(stock=3)
        self.assertEqual(self.labels(), ["Low stock"])

    def test_healthy_product_is_not_an_alert(self):
        make_product(stock=50)
        self.assertEqual(self.labels(), [])

    def test_fast_selling_product_is_an_alert(self):
        # 35 sold in a week = 5 per day, so 20 in stock lasts 4 days
        product = make_product(stock=20)
        Sale.objects.create(product=product, quantity=35, total_price=Decimal("700"))

        self.assertEqual(self.labels(), ["Selling fast"])

    def test_old_sales_are_ignored(self):
        product = make_product(stock=20)
        sale = Sale.objects.create(product=product, quantity=35, total_price=Decimal("700"))
        # move the sale to 30 days ago (outside the 7 day window)
        Sale.objects.filter(pk=sale.pk).update(
            date_sold=timezone.now() - timedelta(days=30)
        )

        self.assertEqual(self.labels(), [])

    def test_most_urgent_comes_first(self):
        make_product(product_id="A", name="Out", stock=0)
        make_product(product_id="B", name="Low", stock=3)
        fast = make_product(product_id="C", name="Fast", stock=20)
        Sale.objects.create(product=fast, quantity=35, total_price=Decimal("700"))

        self.assertEqual(self.labels(), ["Out of stock", "Low stock", "Selling fast"])


# ---------------------------------------------------------------
# 4. Pages (views)
# ---------------------------------------------------------------
class LoginProtectionTests(TestCase):
    def test_pages_send_visitors_to_login(self):
        for name in ["home", "product_list", "sales", "alerts", "scan_page"]:
            url = reverse(name)
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_scan_endpoint_needs_login(self):
        response = self.client.post(
            reverse("scan_sell"),
            data=json.dumps({"barcode": "1111"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)


class PageTests(TestCase):
    def setUp(self):
        User.objects.create_user("shop", password="pass12345")
        self.client.login(username="shop", password="pass12345")

    def test_pages_load_when_signed_in(self):
        for name in ["home", "product_list", "sales", "alerts", "scan_page"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_search_finds_only_matching_products(self):
        make_product(product_id="A", name="Green Tea")
        make_product(product_id="B", name="Coffee Beans")

        response = self.client.get(reverse("product_list"), {"q": "tea"})

        self.assertContains(response, "Green Tea")
        self.assertNotContains(response, "Coffee Beans")

    def test_duplicate_product_id_is_rejected(self):
        make_product(product_id="S1")

        response = self.client.post(
            reverse("product_add"),
            {"product_id": "S1", "name": "Other", "stock": 5, "price": "10"},
        )

        self.assertEqual(response.status_code, 200)  # form shown again
        self.assertEqual(Product.objects.count(), 1)

    def test_delete_needs_post(self):
        product = make_product()
        response = self.client.get(reverse("product_delete", args=[product.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Product.objects.count(), 1)

    def test_sales_page_refuses_too_many(self):
        product = make_product(stock=2)

        response = self.client.post(
            reverse("sales"), {"product": product.pk, "quantity": 99}
        )

        self.assertContains(response, "Only 2 of Tea left.")
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)


# ---------------------------------------------------------------
# 5. Barcode scan
# ---------------------------------------------------------------
class ScanTests(TestCase):
    def setUp(self):
        User.objects.create_user("shop", password="pass12345")
        self.client.login(username="shop", password="pass12345")

    def scan(self, code):
        return self.client.post(
            reverse("scan_sell"),
            data=json.dumps({"barcode": code}),
            content_type="application/json",
        )

    def test_scan_sells_one_unit(self):
        product = make_product(stock=3, barcode="1111")

        response = self.scan("1111")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertEqual(Sale.objects.count(), 1)

    def test_unknown_barcode(self):
        response = self.scan("9999")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["ok"])

    def test_out_of_stock_barcode(self):
        make_product(stock=0, barcode="1111")

        response = self.scan("1111")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Sale.objects.count(), 0)

    def test_scan_rejects_get(self):
        response = self.client.get(reverse("scan_sell"))
        self.assertEqual(response.status_code, 405)