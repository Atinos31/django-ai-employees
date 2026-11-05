"""
Template filters available in every template (registered as builtins
in settings.TEMPLATES), so no {% load %} is needed.
"""

import re
from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def money(value):
    """Format a price: 1099 -> €1,099.00"""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{settings.CURRENCY_SYMBOL}{amount:,.2f}"


@register.filter
def tagline(text):
    """
    First clause of a product description, for short marketing lines:
    "16 inch laptop with Intel Core i7, 32GB RAM, ..." -> "16 inch laptop with Intel Core i7."
    Splits on ", " or ". " so decimals like "6.7 inch" stay intact.
    """
    first = re.split(r",\s|\.\s|\.$", str(text).strip(), maxsplit=1)[0].strip()
    return f"{first}." if first else ""
