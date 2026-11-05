from .cart import CART_SESSION_KEY


def cart_count(request):
    """Number of items in the cart, shown in the navbar on every page."""
    items = request.session.get(CART_SESSION_KEY, {})
    return {"cart_count": sum(items.values())}
