import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ProductForm, SaleForm
from .models import LOW_STOCK_LIMIT, Product, Sale
from .services import LOOKBACK_DAYS, NotEnoughStock, restock_alerts, sell_product


@login_required
def home(request):
    # One number for the whole table: aggregate
    total_products = Product.objects.count()
    low_stock_count = Product.objects.filter(stock__lte=LOW_STOCK_LIMIT).count()
    revenue = Sale.objects.aggregate(total=Sum("total_price"))["total"] or 0

    # A calculated column on every product: annotate
    products = list(
        Product.objects.annotate(units_sold=Sum("sale__quantity")).order_by(
            "-units_sold", "name"
        )
    )

    most = max((p.units_sold or 0 for p in products), default=0)
    chart = [
        {
            "name": p.name,
            "units": p.units_sold or 0,
            "percent": round((p.units_sold or 0) / most * 100) if most else 0,
        }
        for p in products
    ]
    top_seller = products[0] if most else None

    recent_sales = Sale.objects.select_related("product").order_by("-date_sold")[:5]

    return render(
        request,
        "inventory/home.html",
        {
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "revenue": revenue,
            "top_seller": top_seller,
            "chart": chart,
            "recent_sales": recent_sales,
        },
    )

@login_required
def alerts_page(request):
    return render(
        request,
        "inventory/alerts.html",
        {"alerts": restock_alerts(), "days": LOOKBACK_DAYS},
    )



@login_required
def product_list(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.all().order_by("name")
    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(product_id__icontains=query)
        )
    return render(
        request,
        "inventory/product_list.html",
        {"products": products, "query": query},
    )


@login_required
def product_add(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"Added {product.name}.")
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(
        request, "inventory/product_form.html", {"form": form, "title": "Add product"}
    )


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Saved changes to {product.name}.")
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(
        request, "inventory/product_form.html", {"form": form, "title": "Edit product"}
    )


@login_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = product.name
    product.delete()
    messages.success(request, f"Deleted {name}.")
    return redirect("product_list")


@login_required
def sales_page(request):
    if request.method == "POST":
        form = SaleForm(request.POST)
        if form.is_valid():
            try:
                sale = sell_product(
                    form.cleaned_data["product"], form.cleaned_data["quantity"]
                )
            except NotEnoughStock as error:
                form.add_error("quantity", str(error))
            else:
                messages.success(
                    request,
                    f"Sold {sale.quantity} x {sale.product.name} for ₹{sale.total_price}.",
                )
                return redirect("sales")
    else:
        form = SaleForm()

    recent_sales = Sale.objects.select_related("product").order_by("-date_sold")[:20]
    return render(
        request, "inventory/sales.html", {"form": form, "recent_sales": recent_sales}
    )

@login_required
def scan_page(request):
    return render(request, "inventory/scan.html")


@login_required
@require_POST
def scan_sell(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "Bad request."}, status=400)

    code = str(data.get("barcode", "")).strip()
    if not code:
        return JsonResponse({"ok": False, "message": "No barcode received."}, status=400)

    try:
        product = Product.objects.get(barcode=code)
    except Product.DoesNotExist:
        return JsonResponse(
            {"ok": False, "message": f"No product has barcode {code}."}, status=404
        )

    try:
        sale = sell_product(product, 1)
    except NotEnoughStock:
        return JsonResponse(
            {"ok": False, "message": f"{product.name} is out of stock."}, status=409
        )

    return JsonResponse(
        {
            "ok": True,
            "message": (
                f"Sold 1 x {sale.product.name} for ₹{sale.total_price}. "
                f"{sale.product.stock} left."
            ),
        }
    )