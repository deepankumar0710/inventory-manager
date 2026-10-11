# Inventory Manager

A Django web app for a small shop to track products, record sales, see a
dashboard, get restock alerts and sell items by scanning barcodes.

**Live demo:** https://inventory-manager-ulhw.onrender.com/ (free hosting, so the first visit may take about a minute to wake up)

## Features

- Login-protected pages
- Products: add, edit, delete, search, and low-stock labels
- Sales that use an all-or-nothing database transaction with row locking
- Dashboard: product count, low-stock count, revenue, top seller, units-sold chart
- Restock alerts: out of stock, low stock, and "selling fast"
  (a 7-day moving-average forecast of how many days the stock will last)
- Barcode scanning with the camera, or a typed / USB-scanner code
- 27 automated tests

## Tech

Python 3.13, Django 6.1, PostgreSQL (Neon), SQLite for local development, HTML/CSS, JavaScript (html5-qrcode). Deployed on Render.

## Run it locally

```
git clone https://github.com/deepankumar0710/inventory-manager.git
cd inventory-manager
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in.

## Run the tests

```
python manage.py test
```

## Design notes

- **Business rules live in `inventory/services.py`**, not in the views. The
  Sales page and the barcode scan both call the same `sell_product()`.
- **Selling is atomic.** The stock check, the stock change and the sale record
  succeed or fail together (`transaction.atomic()` + `select_for_update()`).
- **Each sale stores its own `total_price`**, so changing a product price later
  does not change past sales.
- **The forecast is a simple moving average**, not machine learning. It ignores
  seasons and festivals.

## Ideas for next steps

- PostgreSQL for production
- Categories, suppliers and purchase orders
- User roles (admin and staff)
- Export reports to CSV
