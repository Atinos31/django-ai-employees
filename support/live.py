"""
Live agent activity for the staff dashboard.

Every agent step is already saved as an AgentLog row and every chat message
as a Message row, so the database is the source of truth. The dashboard
streams rows newer than a cursor ("<last log id>:<last message id>").
Nothing is lost if the server restarts or a browser reconnects: the stream
simply resumes from the last row it sent.
"""

import ast
import json
import re

from django.db.models import Max
from django.utils import timezone

from .models import AgentLog, Message

AGENT_PREFIX = re.compile(r"^\[(Aura|Manager|Risk)\]\s*")
RISK_FINAL = re.compile(r"Final assessment: level=(low|medium|high)(?: score=(\d+))?")
TOOL_CALL = re.compile(r"^Calling (\w+) with (.*)$", re.DOTALL)
TOOL_RESULT = re.compile(r"^(\w+) returned: (.*)$", re.DOTALL)

MAX_DETAIL_CHARS = 700


def _time(value):
    local = timezone.localtime(value)
    return local.isoformat(), local.strftime("%H:%M:%S"), local.strftime("%d %b %Y, %H:%M")


def _truncate(text):
    text = text.strip()
    return text if len(text) <= MAX_DETAIL_CHARS else text[:MAX_DETAIL_CHARS].rstrip() + "…"


def _readable(text):
    """Turn a logged Python dict/list (str(result)) into readable lines."""
    try:
        value = ast.literal_eval(text.strip())  # safe: literals only, never code
    except (ValueError, SyntaxError):
        return text
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            shown = item if isinstance(item, (str, int, float)) else json.dumps(item, ensure_ascii=False)
            lines.append(f"{key}: {shown}")
        return "\n".join(lines)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False, indent=1)
    return text


def describe_log(log):
    """A display-ready dict for one AgentLog row."""
    text = log.message
    match = AGENT_PREFIX.match(text)
    agent = match.group(1) if match else {"manager": "Manager", "risk": "Risk"}.get(log.event_type, "Aura")
    text = AGENT_PREFIX.sub("", text, count=1)

    title, detail = text, ""
    if log.event_type == AgentLog.EventType.TOOL_CALL and (call := TOOL_CALL.match(text)):
        title, detail = f"Uses {call.group(1)}", call.group(2)
    elif log.event_type == AgentLog.EventType.TOOL_RESULT and (result := TOOL_RESULT.match(text)):
        title, detail = f"{result.group(1)} result", _readable(result.group(2))
    elif log.event_type == AgentLog.EventType.FINAL:
        # The reply text itself is shown once, as the chat message
        title, detail = "Replied to the customer", ""
    elif ": " in text:
        title, detail = text.split(": ", 1)

    iso, clock, full = _time(log.created_at)
    event = {
        "kind": "log",
        "id": log.id,
        "conversation_id": log.conversation_id,
        "agent": agent,
        "event_type": log.event_type,
        "title": _truncate(title)[:160],
        "detail": _truncate(detail),
        "time": iso,
        "clock": clock,
        "when": full,
    }
    if risk := RISK_FINAL.search(log.message):
        event["risk_level"] = risk.group(1)
        if risk.group(2):
            event["risk_score"] = int(risk.group(2))
    return event


def describe_message(message):
    """A display-ready dict for one chat Message row."""
    iso, clock, full = _time(message.created_at)
    from_customer = message.role == Message.Role.USER
    return {
        "kind": "message",
        "id": message.id,
        "conversation_id": message.conversation_id,
        "agent": "Customer" if from_customer else "Aura",
        "event_type": "message",
        "title": "Customer wrote" if from_customer else "Aura replied",
        "detail": message.content,
        "time": iso,
        "clock": clock,
        "when": full,
    }


def _add_context(event, conversation):
    event["customer"] = conversation.user.username
    event["order_id"] = conversation.order_id
    return event


def parse_cursor(value):
    """'12:34' -> (12, 34). Anything invalid -> (0, 0)."""
    try:
        log_id, message_id = (int(part) for part in str(value).split(":", 1))
        return max(log_id, 0), max(message_id, 0)
    except (TypeError, ValueError):
        return 0, 0


def format_cursor(log_id, message_id):
    return f"{log_id}:{message_id}"


def current_cursor(conversation_id=None):
    """The cursor pointing after the newest rows, so only new rows are streamed."""
    logs = AgentLog.objects.all()
    messages = Message.objects.all()
    if conversation_id:
        logs = logs.filter(conversation_id=conversation_id)
        messages = messages.filter(conversation_id=conversation_id)
    return format_cursor(
        logs.aggregate(m=Max("id"))["m"] or 0,
        messages.aggregate(m=Max("id"))["m"] or 0,
    )


def events_after(cursor, conversation_id=None, limit=100):
    """
    New events after the cursor, oldest first, plus the cursor to use next.
    Each event carries the cursor up to and including itself as "cursor".
    """
    after_log, after_message = parse_cursor(cursor)

    logs = AgentLog.objects.filter(id__gt=after_log).select_related("conversation__user")
    messages = Message.objects.filter(id__gt=after_message).select_related("conversation__user")
    if conversation_id:
        logs = logs.filter(conversation_id=conversation_id)
        messages = messages.filter(conversation_id=conversation_id)

    rows = [("log", row) for row in logs.order_by("id")[:limit]]
    rows += [("message", row) for row in messages.order_by("id")[:limit]]
    rows.sort(key=lambda item: (item[1].created_at, item[0] == "log", item[1].id))

    events = []
    last_log, last_message = after_log, after_message
    for kind, row in rows:
        if kind == "log":
            event = describe_log(row)
            last_log = max(last_log, row.id)
        else:
            event = describe_message(row)
            last_message = max(last_message, row.id)
        _add_context(event, row.conversation)
        event["cursor"] = format_cursor(last_log, last_message)
        events.append(event)

    return events, format_cursor(last_log, last_message)


def recent_events(limit=25, conversation_id=None):
    """The newest events, oldest first (for the initial page render)."""
    logs = AgentLog.objects.select_related("conversation__user").order_by("-id")
    messages = Message.objects.select_related("conversation__user").order_by("-id")
    if conversation_id:
        logs = logs.filter(conversation_id=conversation_id)
        messages = messages.filter(conversation_id=conversation_id)

    events = [_add_context(describe_log(row), row.conversation) for row in logs[:limit]]
    events += [_add_context(describe_message(row), row.conversation) for row in messages[:limit]]
    events.sort(key=lambda event: event["time"])
    return events[-limit:]


def summarize_conversation(conversation):
    """Badges for the dashboard list: manager involved, risk level, refund outcome."""
    logs = list(conversation.assistant_logs.all())
    messages = list(conversation.messages.all())

    risk_level = None
    for log in logs:
        if match := RISK_FINAL.search(log.message):
            risk_level = match.group(1)

    refunds = [
        refund for refund in conversation.order.refund_requests.all()
        if refund.created_at >= conversation.created_at
    ]
    latest_refund = max(refunds, key=lambda refund: refund.created_at) if refunds else None

    times = [row.created_at for row in logs + messages] or [conversation.created_at]
    customer_messages = [m for m in messages if m.role == Message.Role.USER]
    return {
        "conversation": conversation,
        "manager_involved": any(log.event_type == AgentLog.EventType.MANAGER for log in logs),
        "risk_level": risk_level,
        "refund_status": latest_refund.get_status_display() if latest_refund else None,
        "refund_status_key": latest_refund.status if latest_refund else None,
        "message_count": len(messages),
        "last_customer_message": customer_messages[-1].content if customer_messages else "",
        "last_activity": max(times),
    }
