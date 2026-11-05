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


def record_refund_decision(order, decision, reason, refund_limit):
    """
    Record a manager refund decision for an order.

    decision is "approve", "deny" or "refer". The order always comes
    from the conversation (never from the model), and the rules below
    are enforced here so the model cannot bypass them.
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

    if status == "approved" and order.amount > refund_limit:
        status = "pending"
        referred_for_limit = True

    refund = RefundRequest.objects.create(
        order=order,
        user=order.user,
        reason=reason,
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
    elif status == "pending":
        result["note"] = "The request was referred to human staff for review."
    return result


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
