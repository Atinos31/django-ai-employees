import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from orders.models import Order, RefundRequest

from .tracking_data import DELIVERY_DATA


def get_order_details(order_id):
    """
    Get order details by order ID.
    """
    try:
        order = Order.objects.get(id=order_id)
        return {
            "order_id": order.id,
            "product_name": order.product_name,
            "quantity": order.quantity,
            "amount": str(order.amount),
            "status": order.get_status_display(),
            "carrier": order.carrier,
            "tracking_number": order.tracking_number,
            "delivery_address": order.delivery,
            "ordered_on": order.created_at.strftime("%d %b %Y"),#10 SEPT 2026
            "days_since_ordered":(timezone.now() - order.created_at).days, #20days
        }
    except Order.DoesNotExist:
        return {"error": f"Order with ID {order_id} not found."}

def get_refund_history(user_id):
    """
    Get refund history for a specific user.
    """
    refunds = RefundRequest.objects.filter(user_id=user_id).order_by('-created_at')
    history = []

    for refund in refunds:
        history.append({
            "order_id": refund.order.id,
            "product": refund.order.product_name,
            "reason": refund.reason,
            "status": refund.get_status_display(),
            "requested_on": refund.created_at.strftime("%d %b %Y"),
            "days_since_requested": (timezone.now() - refund.created_at).days,
        })
    return {
        "total_refund_requests":len(history),
        "history": history
    }


def record_refund_decision(order, decision, reason, refund_limit, risk_level=None, customer_claim=""):
    """
    Record a manager refund decision for an order.

    decision is "approve", "deny" or "refer". reason is the internal
    justification (saved as decision_note, never shown to the customer);
    customer_claim is the customer's request in their terms (saved as the
    refund reason and shown on the customer's order page).

    The order always comes from the conversation (never from the model),
    and the rules below are enforced here so the model cannot bypass them:
    - no second refund while one is pending or approved
    - no refunds on cancelled orders
    - approvals above refund_limit go to human staff (pending)
    - approvals for high-risk customers go to human staff (pending)
    """
    existing = order.refund_requests.filter(
        status__in=["pending", "approved"]
    ).first()
    if existing:
        return {
            "error": (
                f"Order #{order.id} already has a refund request "
                f"with status '{existing.get_status_display()}'. "
                "No new refund was recorded."
            )
        }

    if decision == "approve" and order.status == "cancelled":
        return {
            "error": "Cancelled orders cannot be refunded. No refund was recorded."
        }

    status = {"approve": "approved", "deny": "denied", "refer": "pending"}[decision]
    referred_for_limit = False
    referred_for_risk = False

    if status == "approved" and order.amount > refund_limit:
        status = "pending"
        referred_for_limit = True

    if status == "approved" and risk_level == "high":
        status = "pending"
        referred_for_risk = True

    refund = RefundRequest.objects.create(
        order=order,
        user=order.user,
        reason=customer_claim.strip() or "Refund request",
        decision_note=reason,
        status=status,
        created_at=timezone.now(),
    )

    result = {
        "refund_request_id": refund.id,
        "order_id": order.id,
        "amount": str(order.amount),
        "status": refund.get_status_display(),
    }
    if referred_for_limit:
        result["note"] = (
            f"Amount exceeds the manager approval limit of {refund_limit}. "
            "The request was referred to human staff for final approval."
        )
    elif referred_for_risk:
        result["note"] = (
            "The customer's risk level is high, so the approval was referred "
            "to human staff for review. Do not mention risk or fraud checks "
            "to the customer."
        )
    elif status == "pending":
        result["note"] = "The request was referred to human staff for review."
    return result


# ---------------------------------------------------------
# CUSTOMER RISK PROFILE
# ---------------------------------------------------------
# Simple, explainable signals for the Risk Agent. They are indicators
# that a human should look closer, never proof of fraud.

HIGH_VALUE_AMOUNT = Decimal(1000)

NOT_RECEIVED_PHRASES = (
    "not received", "never received", "never arrived", "not arrived",
    "hasn't arrived", "has not arrived", "didn't arrive", "did not arrive",
    "not delivered", "never delivered", "not been delivered", "never came",
)

EMPTY_BOX_PHRASES = (
    "empty box", "box was empty", "arrived empty", "nothing inside",
    "no phone inside", "no laptop inside", "no tablet inside", "box contained nothing",
)

RISK_LEVELS = ("low", "medium", "high")


def _mentions(text, phrases):
    text = (text or "").lower()
    return any(phrase in text for phrase in phrases)


def _normalize_address(address):
    return re.sub(r"[^a-z0-9]+", " ", (address or "").lower()).strip()


def get_customer_risk_profile(user_id):
    """
    Account history and rule-based risk flags for one customer.

    Returns facts (counts, rates, dates) plus a list of flags, each with a
    severity, and a rule_based_level computed from those flags:
    high if any high flag or 3+ medium flags, medium if any medium flag,
    otherwise low.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return {"error": f"Customer {user_id} not found."}

    now = timezone.now()
    last_30 = now - timedelta(days=30)
    last_90 = now - timedelta(days=90)

    orders = list(Order.objects.filter(user=user))
    refunds = list(RefundRequest.objects.filter(user=user).select_related("order"))

    active_orders = [o for o in orders if o.status != "cancelled"]
    high_value_orders = [o for o in active_orders if o.amount >= HIGH_VALUE_AMOUNT]
    addresses = {_normalize_address(o.delivery) for o in active_orders if o.delivery.strip()}

    refunds_last_30 = [r for r in refunds if r.created_at >= last_30]
    refunds_last_90 = [r for r in refunds if r.created_at >= last_90]
    approved_value_90 = sum(
        (r.order.amount for r in refunds_last_90 if r.status == "approved"),
        Decimal(0),
    )
    not_received_on_delivered = [
        r for r in refunds
        if _mentions(r.reason, NOT_RECEIVED_PHRASES) and r.order.status == "delivered"
    ]
    empty_box_claims = [r for r in refunds if _mentions(r.reason, EMPTY_BOX_PHRASES)]
    refund_rate = round(len(refunds) / max(1, len(active_orders)), 2)
    account_age_days = (now - user.date_joined).days

    flags = []

    def flag(code, severity, detail):
        flags.append({"code": code, "severity": severity, "detail": detail})

    if len(refunds_last_30) >= 3:
        flag("refund_burst", "high",
             f"{len(refunds_last_30)} refund requests in the last 30 days")
    elif len(refunds) >= 3:
        flag("many_refunds", "medium", f"{len(refunds)} refund requests in total")

    if len(refunds) >= 2 and refund_rate >= 0.5:
        flag("high_refund_rate", "medium",
             f"Refund requests on {refund_rate:.0%} of non-cancelled orders")

    if len(not_received_on_delivered) >= 2:
        flag("repeated_not_received_on_delivered", "high",
             f"{len(not_received_on_delivered)} 'not received' claims on orders marked delivered")
    elif not_received_on_delivered:
        flag("not_received_on_delivered", "medium",
             "1 'not received' claim on an order marked delivered")

    if empty_box_claims:
        flag("empty_box_claims", "high" if len(empty_box_claims) >= 2 else "medium",
             f"{len(empty_box_claims)} 'empty box' claim(s)")

    if account_age_days < 60 and len(high_value_orders) >= 2:
        flag("new_account_high_value", "medium",
             f"Account is {account_age_days} days old with "
             f"{len(high_value_orders)} orders of {HIGH_VALUE_AMOUNT} EUR or more")

    if len(addresses) >= 3:
        flag("many_delivery_addresses", "medium",
             f"Orders shipped to {len(addresses)} different addresses")

    if approved_value_90 >= 2000:
        flag("large_refunded_value", "medium",
             f"{approved_value_90} EUR refunded in the last 90 days")

    highs = sum(1 for f in flags if f["severity"] == "high")
    mediums = sum(1 for f in flags if f["severity"] == "medium")
    if highs or mediums >= 3:
        level = "high"
    elif mediums:
        level = "medium"
    else:
        level = "low"

    return {
        "customer_id": user.id,
        "account_age_days": account_age_days,
        "total_orders": len(orders),
        "cancelled_orders": len(orders) - len(active_orders),
        "total_spent_eur": str(sum((o.amount for o in active_orders), Decimal(0))),
        "orders_last_30_days": sum(1 for o in orders if o.created_at >= last_30),
        "high_value_orders": len(high_value_orders),
        "distinct_delivery_addresses": len(addresses),
        "refund_requests": {
            "total": len(refunds),
            "approved": sum(1 for r in refunds if r.status == "approved"),
            "denied": sum(1 for r in refunds if r.status == "denied"),
            "pending": sum(1 for r in refunds if r.status == "pending"),
            "last_30_days": len(refunds_last_30),
            "last_90_days": len(refunds_last_90),
        },
        "refund_rate": refund_rate,
        "approved_refund_value_last_90_days_eur": str(approved_value_90),
        "not_received_claims_on_delivered_orders": len(not_received_on_delivered),
        "empty_box_claims": len(empty_box_claims),
        "flags": flags,
        "rule_based_level": level,
        "note": "Signals are indicators for human review, not proof of fraud.",
    }


def check_delivery_status(tracking_number, carrier):
    default_response = {
        "status": "Unknown",
        "last_location": "Tracking information not available",
        "last_update": "N/A",
        "estimated_delivery": "Contact carrier directly for more information",
        "delay_reason": "No updates from the carrier. Please check with them for the latest status.",
    }
    # Copy so we never modify the shared DELIVERY_DATA entries
    result = dict(DELIVERY_DATA.get(tracking_number, default_response))
    result["tracking_number"] = tracking_number
    result["carrier"] = carrier
    return result
