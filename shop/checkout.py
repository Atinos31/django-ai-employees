"""
Stripe Checkout integration.

Flow:
1. create_checkout_session() snapshots the cart (product, quantity and
   price) into the Stripe session metadata and returns Stripe's
   hosted payment page URL.
2. After payment, Stripe redirects back with the session ID.
   fulfill_checkout() asks Stripe whether it was really paid, then
   creates one Order per cart line. It is safe to call more than once
   for the same session.
"""

from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from orders.models import Order, Product


class CheckoutError(Exception):
    """A problem the customer should see as a friendly message."""


def _stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise CheckoutError(
            "Payments are not configured yet. Add STRIPE_SECRET_KEY to .env."
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _to_minor_units(amount):
    """₹34999.00 -> 3499900 (Stripe wants the smallest currency unit)."""
    return int((amount * 100).quantize(Decimal("1")))


def create_checkout_session(*, user, cart_lines, address, success_url, cancel_url):
    if not cart_lines:
        raise CheckoutError("Your bag is empty.")

    for line in cart_lines:
        if not line["product"].in_stock:
            raise CheckoutError(
                f"{line['product'].name} is out of stock. "
                "Remove it from your bag to continue."
            )

    # "product_id:quantity:unit_price;..." so the orders match exactly
    # what the customer was charged, even if prices change later.
    cart_snapshot = ";".join(
        f"{line['product'].id}:{line['quantity']}:{line['product'].price}"
        for line in cart_lines
    )

    session = _stripe().checkout.Session.create(
        mode="payment",
        customer_email=user.email or None,
        client_reference_id=str(user.id),
        line_items=[
            {
                "quantity": line["quantity"],
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY,
                    "unit_amount": _to_minor_units(line["product"].price),
                    "product_data": {"name": line["product"].name},
                },
            }
            for line in cart_lines
        ],
        metadata={
            "user_id": str(user.id),
            "cart": cart_snapshot,
            "address": address,
        },
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
    )
    return session.url


def fulfill_checkout(*, session_id, user):
    """Create orders for a paid Stripe session. Returns the orders."""

    session = _stripe().checkout.Session.retrieve(session_id)

    # In current stripe-python (16.x here) StripeObject is not a dict subclass,
    # so dict methods like .get() raise AttributeError. Convert to a plain dict.
    raw_metadata = session.metadata or {}
    metadata = (
        raw_metadata.to_dict() if hasattr(raw_metadata, "to_dict") else dict(raw_metadata)
    )

    if metadata.get("user_id") != str(user.id):
        raise CheckoutError("This payment does not belong to your account.")

    if session.payment_status != "paid":
        raise CheckoutError(
            "We have not received your payment yet. "
            "If you were charged, please contact support."
        )

    with transaction.atomic():
        # Lock the customer's row so two simultaneous requests for the
        # same session cannot both create orders.
        User.objects.select_for_update().get(id=user.id)

        existing = list(Order.objects.filter(stripe_session_id=session.id))
        if existing:
            return existing

        now = timezone.now()
        orders = []

        for item in metadata["cart"].split(";"):
            product_id, quantity, unit_price = item.split(":")
            quantity = int(quantity)
            product = Product.objects.filter(id=int(product_id)).first()

            orders.append(Order.objects.create(
                user=user,
                product=product,
                product_name=product.name if product else f"Product #{product_id}",
                quantity=quantity,
                amount=Decimal(unit_price) * quantity,
                status="pending",
                delivery=metadata.get("address", ""),
                stripe_session_id=session.id,
                created_at=now,
            ))

    return orders
