from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from orders.models import Product

from .cart import MAX_QUANTITY, Cart


def product_list(request):
    products = Product.objects.order_by("category", "price")
    categories = products.values_list("category", flat=True).distinct()

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
    })


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if not product.in_stock:
        messages.error(request, f"{product.name} is out of stock.")
    else:
        Cart(request).add(product)
        messages.success(request, f"Added {product.name} to your cart.")

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
