from django.utils import timezone
from orders.models import Order, RefundRequest


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
