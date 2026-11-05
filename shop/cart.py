from decimal import Decimal

from orders.models import Product

CART_SESSION_KEY = "cart"
MAX_QUANTITY = 5


class Cart:
    """
    Shopping cart stored in the session as {"<product_id>": quantity}.

    Prices are never stored in the session; they are always read from
    the database, so a customer cannot change what they pay.
    """

    def __init__(self, request):
        self.session = request.session
        self.items = self.session.setdefault(CART_SESSION_KEY, {})

    def _save(self):
        self.session.modified = True

    def add(self, product, quantity=1):
        key = str(product.id)
        new_quantity = self.items.get(key, 0) + quantity
        self.items[key] = max(1, min(new_quantity, MAX_QUANTITY))
        self._save()

    def set(self, product_id, quantity):
        key = str(product_id)
        if key not in self.items:
            return
        if quantity <= 0:
            del self.items[key]
        else:
            self.items[key] = min(quantity, MAX_QUANTITY)
        self._save()

    def remove(self, product_id):
        self.items.pop(str(product_id), None)
        self._save()

    def clear(self):
        self.items.clear()
        self._save()

    def lines(self):
        """Cart lines with current products and prices from the database."""
        products = Product.objects.in_bulk(
            [int(key) for key in self.items]
        )

        # Drop products that were deleted since they were added
        for key in list(self.items):
            if int(key) not in products:
                del self.items[key]
                self._save()

        return [
            {
                "product": products[int(key)],
                "quantity": quantity,
                "line_total": products[int(key)].price * quantity,
            }
            for key, quantity in self.items.items()
        ]

    def total(self):
        return sum(
            (line["line_total"] for line in self.lines()),
            Decimal("0.00"),
        )

    def count(self):
        return sum(self.items.values())
