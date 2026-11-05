"""
Staff dashboard: conversations, agent activity and a live stream (SSE).

The stream is designed to be safe on a single Gunicorn worker:
- staff only (customer data and internal reasoning are shown)
- a heartbeat comment keeps proxies from closing idle connections
- each stream ends after STREAM_MAX_SECONDS; the browser reconnects on its
  own and resumes from the last event (Last-Event-ID), so nothing is lost
- at most MAX_LIVE_STREAMS streams run at once; extra tabs are told to
  poll the JSON endpoint instead, so open dashboards never starve the chat
"""

import json
import threading
import time

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render

from .live import (
    current_cursor,
    describe_log,
    describe_message,
    events_after,
    recent_events,
    summarize_conversation,
)
from .models import Conversation

STREAM_MAX_SECONDS = 120
STREAM_POLL_SECONDS = 1.0
STREAM_HEARTBEAT_SECONDS = 15
MAX_LIVE_STREAMS = 4
POLL_FALLBACK_MILLISECONDS = 4000

_stream_slots = threading.BoundedSemaphore(MAX_LIVE_STREAMS)


def _conversation_filter(request):
    try:
        return int(request.GET.get("conversation", "")) or None
    except ValueError:
        return None


@staff_member_required
def dashboard(request):
    conversations = (
        Conversation.objects.select_related("user", "order")
        .prefetch_related("assistant_logs", "messages", "order__refund_requests")
        .order_by("-created_at")[:50]
    )
    rows = sorted(
        (summarize_conversation(conversation) for conversation in conversations),
        key=lambda row: row["last_activity"],
        reverse=True,
    )
    return render(request, "support/dashboard.html", {
        "rows": rows,
        "feed": list(reversed(recent_events(limit=25))),
        "cursor": current_cursor(),
        "poll_ms": POLL_FALLBACK_MILLISECONDS,
    })


@staff_member_required
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("user", "order")
        .prefetch_related("assistant_logs", "messages", "order__refund_requests"),
        id=conversation_id,
    )
    return render(request, "support/conversation_detail.html", {
        "summary": summarize_conversation(conversation),
        "conversation": conversation,
        # Not "messages": base.html uses that name for flash notices
        "chat_messages": [describe_message(m) for m in conversation.messages.all()],
        "steps": [describe_log(log) for log in conversation.assistant_logs.all()],
        "cursor": current_cursor(conversation.id),
        "poll_ms": POLL_FALLBACK_MILLISECONDS,
    })


@staff_member_required
def events(request):
    """JSON fallback for browsers that cannot hold a live stream."""
    found, cursor = events_after(request.GET.get("cursor", ""), _conversation_filter(request))
    return JsonResponse({"events": found, "cursor": cursor})


@staff_member_required
def stream(request):
    """Server-Sent Events: new agent steps and chat messages as they happen."""
    conversation_id = _conversation_filter(request)
    # On reconnect the browser sends the id of the last event it received
    cursor = request.headers.get("Last-Event-ID") or request.GET.get("cursor", "")

    def generate():
        nonlocal cursor
        # Take a slot only once streaming starts, so it is always released
        if not _stream_slots.acquire(blocking=False):
            yield f"data: {json.dumps({'type': 'busy'})}\n\n"
            return
        try:
            yield "retry: 3000\n\n"
            started = last_beat = time.monotonic()
            while time.monotonic() - started < STREAM_MAX_SECONDS:
                found, cursor = events_after(cursor, conversation_id)
                for event in found:
                    yield f"id: {event['cursor']}\ndata: {json.dumps(event)}\n\n"
                    last_beat = time.monotonic()
                if time.monotonic() - last_beat >= STREAM_HEARTBEAT_SECONDS:
                    yield ": keep-alive\n\n"
                    last_beat = time.monotonic()
                time.sleep(STREAM_POLL_SECONDS)
        finally:
            _stream_slots.release()

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # stop proxies from buffering the stream
    return response
