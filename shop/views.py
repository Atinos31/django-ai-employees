import logging

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from orders.models import Product

from .cart import MAX_QUANTITY, Cart
from .checkout import CheckoutError, create_checkout_session, fulfill_checkout

logger = logging.getLogger(__name__)


def home(request):
    """Landing page: a hero product plus one tile per category."""
    products = Product.objects.filter(in_stock=True).order_by("-price")

    hero = products.filter(category="TVs").first() or products.first()

    tiles = []
    seen = {hero.category} if hero else set()
    for product in products:
        if product.category not in seen:
            seen.add(product.category)
            tiles.append(product)

    return render(request, "home.html", {"hero": hero, "tiles": tiles[:4]})


def product_list(request):
    products = Product.objects.order_by("category", "price")
    # Order by category only: Django adds ORDER BY columns to DISTINCT,
    # so ordering by price here would repeat each category per price.
    categories = (
        Product.objects.order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )

    selected_category = request.GET.get("category", "")
    if selected_category:
        products = products.filter(category=selected_category)

    return render(request, "shop.html", {
        "products": products,
        "categories": categories,
        "selected_category": selected_category,
    })


def cart_detail(request):
    cart = Cart(request)
    return render(request, "cart.html", {
        "lines": cart.lines(),
        "total": cart.total(),
        "max_quantity": MAX_QUANTITY,
        "quantity_range": range(1, MAX_QUANTITY + 1),
        "delivery_address": request.session.get("delivery_address", ""),
    })


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if not product.in_stock:
        messages.error(request, f"{product.name} is out of stock.")
    else:
        Cart(request).add(product)
        messages.success(request, f"Added {product.name} to your bag.")

    # Only redirect back to pages on this site
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("product_list")


@require_POST
def cart_update(request, product_id):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except ValueError:
        quantity = 1

    Cart(request).set(product_id, quantity)
    return redirect("cart_detail")


@require_POST
def cart_remove(request, product_id):
    Cart(request).remove(product_id)
    return redirect("cart_detail")


# ---------------------------------------------------------
# CHECKOUT
# ---------------------------------------------------------

@login_required
@require_POST
def checkout(request):
    cart = Cart(request)
    address = request.POST.get("address", "").strip()

    if len(address) < 10:
        messages.error(request, "Please enter your full delivery address.")
        return redirect("cart_detail")

    # Remember the address so the form is pre-filled if they come back
    request.session["delivery_address"] = address[:400]

    try:
        payment_url = create_checkout_session(
            user=request.user,
            cart_lines=cart.lines(),
            address=address[:400],
            success_url=request.build_absolute_uri(reverse("checkout_success")),
            cancel_url=request.build_absolute_uri(reverse("checkout_cancelled")),
        )
    except CheckoutError as error:
        messages.error(request, str(error))
        return redirect("cart_detail")
    except stripe.StripeError:
        logger.exception("Stripe checkout session failed")
        messages.error(request, "We couldn't start the payment. Please try again.")
        return redirect("cart_detail")

    return redirect(payment_url, permanent=False)


@login_required
def checkout_success(request):
    session_id = request.GET.get("session_id", "")
    if not session_id:
        return redirect("cart_detail")

    try:
        orders = fulfill_checkout(session_id=session_id, user=request.user)
    except CheckoutError as error:
        messages.error(request, str(error))
        return redirect("cart_detail")
    except stripe.StripeError:
        logger.exception("Stripe checkout fulfillment failed")
        messages.error(
            request,
            "We couldn't confirm your payment. If you were charged, please contact support.",
        )
        return redirect("cart_detail")
    except Exception:
        # The customer may already have paid: never show a raw error page.
        # Log everything and give them a reference support can look up.
        logger.exception("Unexpected error fulfilling Stripe session %s", session_id)
        messages.error(
            request,
            "Your payment may have gone through, but we couldn't confirm your order. "
            f"Please contact support with reference {session_id[-10:]}.",
        )
        return redirect("cart_detail")

    Cart(request).clear()

    return render(request, "checkout_success.html", {
        "orders": orders,
        "total": sum(order.amount for order in orders),
    })


@login_required
def checkout_cancelled(request):
    messages.info(request, "Payment cancelled. Your bag is still here.")
    return redirect("cart_detail")
