import logging

from anthropic import Anthropic
from django.conf import settings

from .models import Conversation, AgentLog
from .tools import (
    check_delivery_status,
    get_order_details,
    get_refund_history,
    record_refund_decision,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# ANTHROPIC CLIENT
# ---------------------------------------------------------

client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY
)

anthropic_model = settings.ANTHROPIC_MODEL


# ---------------------------------------------------------
# SUPPORT AGENT SYSTEM PROMPT
# ---------------------------------------------------------

SUPPORT_SYSTEM_PROMPT = """
You are Aura, a customer support agent at CoolBreeze AC.

You help customers with issues related to their AC orders.

Your responsibilities:

- Use available tools when you need factual information.
- Check order details when a customer asks about their order.
- Check refund history before discussing previous refunds.
- Check delivery status when a customer asks about shipping.
- Be empathetic but honest.

Your personality:

- Friendly and professional.
- Patient even when the customer is angry.
- Clear and concise.
- Do not use emojis.

Important rules:

- Never invent order information.
- Use tools when information must be retrieved from the database.
- If you do not know something, say so.
- Never use bold text, bullet points, or markdown in the final customer reply.
- Keep responses concise and conversational.
- Maximum 3-4 sentences.

Escalation:

- You cannot approve or deny refunds yourself, and you must never promise one.
- Use escalate_to_manager when the customer asks for a refund or compensation,
  reports a damaged or faulty product, or has a problem you cannot resolve
  with your tools.
- Gather the key facts with your tools before escalating.
- The tool returns the manager's decision. Pass it on to the customer honestly
  and in your own words, without exposing internal notes or limits.
- Only describe actions that actually happened according to tool results.
  Never claim you updated, added to, or flagged a case unless a tool did it.
"""


# ---------------------------------------------------------
# CLAUDE TOOL DEFINITIONS
# ---------------------------------------------------------
# The lookup tools take no order or user IDs. They always act on the
# order attached to the conversation, so the model cannot be talked
# into reading another customer's data.

ORDER_LOOKUP_TOOLS = [

    {
        "name": "get_order_details",
        "description": (
            "Fetch full details of the order in this conversation: status, "
            "amount, carrier, tracking number, delivery address and dates."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },

    {
        "name": "get_refund_history",
        "description": "Get all previous refund requests made by this customer.",
        "input_schema": {"type": "object", "properties": {}},
    },

    {
        "name": "check_delivery_status",
        "description": "Check the carrier's current delivery status for this order.",
        "input_schema": {"type": "object", "properties": {}},
    },

]


def execute_order_lookup_tool(order, tool_name):
    """Run a lookup tool against the conversation's order, or return None."""

    if tool_name == "get_order_details":
        return get_order_details(order.id)

    if tool_name == "get_refund_history":
        return get_refund_history(order.user_id)

    if tool_name == "check_delivery_status":
        if not order.tracking_number:
            return {"error": "This order has no tracking number yet."}
        return check_delivery_status(order.tracking_number, order.carrier)

    return None


SUPPORT_TOOLS = ORDER_LOOKUP_TOOLS + [

    {
        "name": "escalate_to_manager",

        "description": (
            "Escalate this conversation to the Manager Agent. Use for refund "
            "or compensation requests, damaged or faulty products, and issues "
            "you cannot resolve. Returns the manager's decision and guidance."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "request_type": {
                    "type": "string",
                    "enum": ["refund", "damaged_product", "complaint", "other"],
                    "description": "The kind of issue being escalated",
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "Summary of the customer's problem, what they are asking "
                        "for, and the relevant facts you already found"
                    ),
                },
            },

            "required": ["request_type", "summary"],
        },
    },

]


# ---------------------------------------------------------
# MANAGER AGENT SYSTEM PROMPT
# ---------------------------------------------------------

MANAGER_SYSTEM_PROMPT = """
You are the Support Manager at CoolBreeze AC. The front-line support agent,
Aura, escalates cases to you. You never talk to the customer directly; your
reply goes back to Aura.

Your job is to decide escalated cases fairly and consistently.

Process:

1. Always call get_order_details and get_refund_history before deciding.
2. Call check_delivery_status when delivery is relevant to the case.
3. For refund or damaged product cases, record exactly one decision with
   record_refund_decision. For other cases, give guidance without recording
   a decision.

Refund policy:

- Approve when the product arrived damaged or faulty, or when the order has
  not been delivered more than 14 days after it was placed.
- Deny change-of-mind requests made more than 30 days after the order date,
  and requests on cancelled orders.
- Refer to human staff ("refer") if the customer has 3 or more previous refund
  requests, if the facts are unclear or contradictory, or if the case is not
  covered by this policy.
- If the order already has a pending or approved refund, do not record a new
  decision; report the existing status instead.

Your final reply to Aura must be short plain text containing:
the decision, the reason, and what Aura should tell the customer.
"""


# ---------------------------------------------------------
# MANAGER TOOL DEFINITIONS
# ---------------------------------------------------------

MANAGER_TOOLS = ORDER_LOOKUP_TOOLS + [

    {
        "name": "record_refund_decision",
        "description": (
            "Record the refund decision for this order. Approvals above the "
            "manager's limit are automatically sent to human staff."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approve", "deny", "refer"],
                    "description": "approve, deny, or refer to human staff",
                },
                "reason": {
                    "type": "string",
                    "description": "Short justification based on the refund policy",
                },
            },
            "required": ["decision", "reason"],
        },
    },

]


# ---------------------------------------------------------
# SHARED AGENT LOOP
# ---------------------------------------------------------

MAX_AGENT_TURNS = 10


def run_agent_loop(
    *,
    agent_name,
    system,
    tools,
    messages,
    conversation,
    execute_tool,
    final_event_type,
):
    """
    Call Claude, run any requested tools, and repeat until Claude
    gives a final text answer. Every step is written to AgentLog.
    """

    for _ in range(MAX_AGENT_TURNS):

        response = client.messages.create(
            model=anthropic_model,
            max_tokens=1024,
            system=system,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            break

        messages.append({
            "role": "assistant",
            "content": response.content,
        })

        tool_results = []

        for block in response.content:

            if block.type != "tool_use":
                continue

            logger.info("%s requested tool: %s", agent_name, block.name)

            AgentLog.objects.create(
                conversation=conversation,
                event_type=AgentLog.EventType.TOOL_CALL,
                message=f"[{agent_name}] Calling {block.name} with {block.input}",
            )

            result = execute_tool(block.name, block.input)

            AgentLog.objects.create(
                conversation=conversation,
                event_type=AgentLog.EventType.TOOL_RESULT,
                message=f"[{agent_name}] {block.name} returned: {str(result)[:500]}",
            )

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })

        messages.append({
            "role": "user",
            "content": tool_results,
        })

    else:
        logger.warning(
            "%s hit the %s turn limit in conversation %s",
            agent_name, MAX_AGENT_TURNS, conversation.id,
        )

    final_reply = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    AgentLog.objects.create(
        conversation=conversation,
        event_type=final_event_type,
        message=f"[{agent_name}] {final_reply}",
    )

    return final_reply


# ---------------------------------------------------------
# MANAGER AGENT
# ---------------------------------------------------------

def run_manager_agent(conversation, request_type, summary):

    order = conversation.order
    decision_recorded = False

    def execute_manager_tool(tool_name, tool_input):
        nonlocal decision_recorded

        result = execute_order_lookup_tool(order, tool_name)
        if result is not None:
            return result

        if tool_name == "record_refund_decision":
            decision_recorded = True
            return record_refund_decision(
                order=order,
                decision=tool_input["decision"],
                reason=tool_input["reason"],
                refund_limit=settings.MANAGER_REFUND_LIMIT,
            )

        return {"error": f"Unknown tool: {tool_name}"}

    AgentLog.objects.create(
        conversation=conversation,
        event_type=AgentLog.EventType.MANAGER,
        message=f"[Manager] Escalation received ({request_type}): {summary}",
    )

    decision = run_agent_loop(
        agent_name="Manager",
        system=MANAGER_SYSTEM_PROMPT,
        tools=MANAGER_TOOLS,
        messages=[{
            "role": "user",
            "content": (
                f"Escalated case for Order #{order.id}.\n"
                f"Request type: {request_type}\n"
                f"Aura's summary: {summary}"
            ),
        }],
        conversation=conversation,
        execute_tool=execute_manager_tool,
        final_event_type=AgentLog.EventType.MANAGER,
    )

    # Refund cases must always leave a record staff can act on. If the
    # model skipped record_refund_decision, refer the case to humans.
    if request_type in ("refund", "damaged_product") and not decision_recorded:
        result = record_refund_decision(
            order=order,
            decision="refer",
            reason=f"Auto-referred (no manager decision recorded). {summary}",
            refund_limit=settings.MANAGER_REFUND_LIMIT,
        )
        AgentLog.objects.create(
            conversation=conversation,
            event_type=AgentLog.EventType.MANAGER,
            message=f"[Manager] No decision recorded; auto-referred: {result}",
        )

    return decision or (
        "The manager could not reach a decision. Tell the customer their case "
        "has been passed to the support team, who will follow up."
    )


# ---------------------------------------------------------
# SUPPORT AGENT (AURA)
# ---------------------------------------------------------

def run_support_agent(
    user_message,
    conversation_id,
    order_id,
    user_id,
):

    conversation = Conversation.objects.select_related("order").get(
        id=conversation_id
    )

    def execute_support_tool(tool_name, tool_input):

        result = execute_order_lookup_tool(conversation.order, tool_name)
        if result is not None:
            return result

        if tool_name == "escalate_to_manager":
            return {
                "manager_decision": run_manager_agent(
                    conversation,
                    tool_input["request_type"],
                    tool_input["summary"],
                )
            }

        return {"error": f"Unknown tool: {tool_name}"}

    messages = [
        {"role": message.role, "content": message.content}
        for message in conversation.messages.order_by("created_at")
    ]

    final_reply = run_agent_loop(
        agent_name="Aura",
        system=(
            SUPPORT_SYSTEM_PROMPT
            + f"\n\nContext: This conversation is about Order #{order_id}, "
            f"customer user ID {user_id}."
        ),
        tools=SUPPORT_TOOLS,
        messages=messages,
        conversation=conversation,
        execute_tool=execute_support_tool,
        final_event_type=AgentLog.EventType.FINAL,
    )

    logger.info("Support agent completed conversation %s", conversation_id)

    return final_reply or (
        "Sorry, I couldn't generate a response. Could you rephrase that?"
    )


