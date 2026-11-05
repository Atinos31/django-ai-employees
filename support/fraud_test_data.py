"""
Demo customers with realistic risk patterns, for testing the Risk Agent.

Used by the seed_fraud_data management command and by the tests.
All dates are relative to "now", so patterns such as "3 refunds in the
last 30 days" stay true whenever the data is created.

These are fictional demo accounts for local development only.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from orders.models import Order, Product, RefundRequest

DEMO_EMAIL_DOMAIN = "@example.com"
DEFAULT_PASSWORD = "VoltHub-demo-2026"

ADDRESSES = {
    "antwerp": "Meir 50\n2000 Antwerp\nBelgium",
    "rotterdam": "Coolsingel 40\n3011 AD Rotterdam\nNetherlands",
    "brussels": "Rue Neuve 1\n1000 Brussels\nBelgium",
    "lille": "Rue Faidherbe 12\n59000 Lille\nFrance",
    "vienna": "Mariahilfer Strasse 20\n1070 Vienna\nAustria",
    "copenhagen": "Vesterbrogade 15\n1620 Copenhagen\nDenmark",
}

# Each order: (key, product name, days ago, address, carrier, tracking number, status)
# Each refund: (order key, customer's reason, status, days ago)
# The last order of each customer is the "live case" to chat about.
DEMO_CUSTOMERS = [
    {
        "username": "marco",
        "first_name": "Marco",
        "joined_days_ago": 26,
        "expected_risk": "high",
        "live_case": "Says the phone never arrived, but the carrier recorded a signed delivery.",
        "orders": [
            ("phone_pro", "VoltHub Nova Pro 5G Phone 256GB", 24, "antwerp", "DHL Express", "JJD150000111", "delivered"),
            ("airbook", "VoltHub AirBook 14 Laptop", 21, "rotterdam", "DPD", "DPD05900000112", "delivered"),
            ("buds", "VoltHub Buds Pro Wireless Earbuds", 17, "brussels", "bpost", "BP900000113BE", "delivered"),
            ("probook", "VoltHub ProBook 16 Laptop", 14, "lille", "DHL Express", "JJD150000114", "delivered"),
            ("phone", "VoltHub Nova 5G Phone 128GB", 5, "antwerp", "DHL Express", "JJD150000115", "delivered"),
        ],
        "refunds": [
            ("phone_pro", "The box arrived empty, there was no phone inside.", "approved", 20),
            ("airbook", "The laptop never arrived.", "denied", 16),
            ("buds", "Earbuds not received.", "pending", 12),
            ("probook", "The laptop arrived with a cracked screen.", "approved", 9),
        ],
    },
    {
        "username": "tomas",
        "first_name": "Tomas",
        "joined_days_ago": 210,
        "expected_risk": "medium",
        "live_case": "Tablet stopped charging after a week (a normal fault claim).",
        "orders": [
            ("phone", "VoltHub Nova 5G Phone 128GB", 180, "vienna", "DPD", "DPD05900000201", "delivered"),
            ("buds", "VoltHub Buds Pro Wireless Earbuds", 120, "vienna", "DPD", "DPD05900000202", "delivered"),
            ("tv", "VoltHub Vision 43\" 4K Smart TV", 60, "vienna", "DPD", "DPD05900000203", "delivered"),
            ("charger", "VoltHub 25W USB-C Fast Charger", 30, "vienna", "DPD", "DPD05900000204", "delivered"),
            ("tablet", "VoltHub Tab 11 Tablet", 8, "vienna", "DPD", "DPD05900000205", "delivered"),
        ],
        "refunds": [
            ("phone", "Battery drains fast after a month.", "denied", 175),
            ("buds", "Changed my mind, the sound is not for me.", "approved", 115),
            ("tv", "The TV has a vertical line of dead pixels.", "approved", 50),
        ],
    },
    {
        "username": "nina",
        "first_name": "Nina",
        "joined_days_ago": 760,
        "expected_risk": "low",
        "live_case": "TV arrived with a cracked screen (a loyal customer's first claim in two years).",
        "orders": [
            ("qled", "VoltHub Vision 55\" QLED TV", 700, "copenhagen", "DHL Express", "JJD150000301", "delivered"),
            ("buds", "VoltHub Buds Pro Wireless Earbuds", 500, "copenhagen", "DHL Express", "JJD150000302", "delivered"),
            ("tablet", "VoltHub Tab 11 Tablet", 300, "copenhagen", "DHL Express", "JJD150000303", "delivered"),
            ("charger", "VoltHub 25W USB-C Fast Charger", 200, "copenhagen", "DHL Express", "JJD150000304", "delivered"),
            ("phone_pro", "VoltHub Nova Pro 5G Phone 256GB", 90, "copenhagen", "DHL Express", "JJD150000305", "delivered"),
            ("tv", "VoltHub Vision 43\" 4K Smart TV", 4, "copenhagen", "DHL Express", "JJD150000306", "delivered"),
        ],
        "refunds": [
            ("qled", "The TV arrived with a dented frame.", "approved", 695),
        ],
    },
]

DEMO_USERNAMES = [customer["username"] for customer in DEMO_CUSTOMERS]


class DemoDataError(Exception):
    pass


def _demo_users():
    """Existing demo users, refusing to touch real accounts with the same name."""
    users = list(User.objects.filter(username__in=DEMO_USERNAMES))
    for user in users:
        if not user.email.endswith(DEMO_EMAIL_DOMAIN):
            raise DemoDataError(
                f"User '{user.username}' exists and is not a demo account "
                f"(email does not end with {DEMO_EMAIL_DOMAIN}). Nothing was changed."
            )
    return users


def remove_fraud_test_data():
    """Delete the demo customers (their orders, refunds and chats cascade)."""
    users = _demo_users()
    count = len(users)
    for user in users:
        user.delete()
    return count


@transaction.atomic
def seed_fraud_test_data(password=DEFAULT_PASSWORD, now=None):
    """
    Create (or recreate) the demo customers. Returns a summary per customer,
    including the order ID of the live case to chat about.
    """
    now = now or timezone.now()
    remove_fraud_test_data()

    products = {p.name: p for p in Product.objects.all()}
    summary = []

    for spec in DEMO_CUSTOMERS:
        user = User.objects.create_user(
            username=spec["username"],
            email=f"{spec['username']}{DEMO_EMAIL_DOMAIN}",
            password=password,
            first_name=spec["first_name"],
        )
        user.date_joined = now - timedelta(days=spec["joined_days_ago"])
        user.save(update_fields=["date_joined"])

        orders = {}
        for key, product_name, days_ago, address, carrier, tracking, status in spec["orders"]:
            product = products.get(product_name)
            if product is None:
                raise DemoDataError(
                    f"Product '{product_name}' not found. Load the demo data first: "
                    "python manage.py loaddata demo_data"
                )
            orders[key] = Order.objects.create(
                user=user,
                product=product,
                product_name=product.name,
                quantity=1,
                amount=product.price,
                status=status,
                carrier=carrier,
                tracking_number=tracking,
                delivery=ADDRESSES[address],
                created_at=now - timedelta(days=days_ago),
            )

        for order_key, reason, status, days_ago in spec["refunds"]:
            RefundRequest.objects.create(
                order=orders[order_key],
                user=user,
                reason=reason,
                status=status,
                created_at=now - timedelta(days=days_ago),
            )

        live_key = spec["orders"][-1][0]
        summary.append({
            "username": user.username,
            "expected_risk": spec["expected_risk"],
            "live_case_order_id": orders[live_key].id,
            "live_case": spec["live_case"],
        })

    return summary
