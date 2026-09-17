from venv import logger

from anthropic import Anthropic
from django.conf import settings

from .models import Conversation, AgentLog
from .tools import (
    get_order_details,
    get_refund_history,
    check_delivery_status,
)


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
"""


# ---------------------------------------------------------
# CLAUDE TOOL DEFINITIONS
# ---------------------------------------------------------

SUPPORT_TOOLS = [

    {
        "name": "get_order_details",

        "description": (
            "Fetch complete order details including status, "
            "carrier, tracking number and information about "
            "the customer's order."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "The order ID to look up",
                }
            },

            "required": ["order_id"],
        },
    },


    {
        "name": "get_refund_history",

        "description": (
            "Get the refund history for a customer. "
            "Use this when information about previous refunds "
            "is needed."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The user ID whose refund history should be checked",
                }
            },

            "required": ["user_id"],
        },
    },


    {
        "name": "check_delivery_status",

        "description": (
            "Check the current delivery status using "
            "the tracking number and carrier."
        ),

        "input_schema": {
            "type": "object",

            "properties": {

                "tracking_number": {
                    "type": "string",
                    "description": "The shipment tracking number",
                },

                "carrier": {
                    "type": "string",
                    "description": "The carrier name",
                },

            },

            "required": [
                "tracking_number",
                "carrier",
            ],
        },
    },

]


# ---------------------------------------------------------
# TOOL EXECUTION
# ---------------------------------------------------------

def execute_tool(tool_name, tool_input):
    if tool_name == "get_order_details":

        result = get_order_details(
            tool_input["order_id"]
        )


    elif tool_name == "get_refund_history":

        result = get_refund_history(
            tool_input["user_id"]
        )


    elif tool_name == "check_delivery_status":

        result = check_delivery_status(
            tool_input["tracking_number"],
            tool_input["carrier"],
        )


    else:

        result = {
            "error": f"Unknown tool: {tool_name}"
        }

    return result


# ---------------------------------------------------------
# SUPPORT AGENT
# ---------------------------------------------------------
def run_support_agent(
    user_message,
    conversation_id,
    order_id,
    user_id,
):

    conversation = Conversation.objects.get(
        id=conversation_id
    )

    conversation_messages = []

    for message in conversation.messages.order_by(
        "created_at"
    ):

        role = message.role
        if role == "agent":
            role = "assistant"

        conversation_messages.append({
            "role": role,
            "content": message.content,
        })
    while True:
        # send this conversation to LLM
        response = client.messages.create(
            model=anthropic_model,
            max_tokens=1024,
            system=(
                SUPPORT_SYSTEM_PROMPT
                + f"""Current context:Order ID: {order_id}Customer User ID: {user_id}"""
            ),
            tools=SUPPORT_TOOLS,
            messages=conversation_messages,
        )

        if response.stop_reason == "tool_use":

            tool_results = []

            conversation_messages.append({
                "role": "assistant",
                "content": response.content,
            })

            for block in response.content:

                if block.type != "tool_use":
                    continue

                logger.info(
                    "Agent requested tool: %s",
                    block.name,
                )

                AgentLog.objects.create(
                    conversation=conversation,
                    event_type="tool_call",
                    message=(
                        f"Calling tool "
                        f"{block.name} "
                        f"with {block.input}"
                    ),
                )

                result = execute_tool(
                    block.name,
                    block.input,
                )

                AgentLog.objects.create(
                    conversation=conversation,
                    event_type="tool_result",
                    message=(
                        f"{block.name} returned: "
                        f"{str(result)[:500]}"
                    ),
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

            conversation_messages.append({
                "role": "user",
                "content": tool_results,
            })

            continue

        final_reply = ""

        for block in response.content:

            if block.type == "text":
                final_reply += block.text

        final_reply = final_reply.strip()

        AgentLog.objects.create(
            conversation=conversation,
            event_type="final",
            message=final_reply,
        )

        logger.info(
            "Support agent completed conversation %s",
            conversation_id,
        )

        return final_reply