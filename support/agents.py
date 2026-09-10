from anthropic import Anthropic
from django.conf import settings

from .tools import check_delivery_status, get_order_details, get_refund_history

# initialize the Anthropic client with the API key from settings
client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

anthropic_model = settings.ANTHROPIC_MODEL  # Use the model specified in settings

# SUPPORT SYSTEM PROMPT --> AGRENT AURA job description and instructions for the AI agent to follow when interacting with the user and executing tasks. This prompt will be used to guide the AI agent's behavior and ensure it adheres to the desired workflow and objectives.

SUPPORT_SYSTEM_PROMPT = """
You are Aura, a customer support agent at CoolBreeze AC.
You help customers with issues related to their AC orders.

Your responsibilities:
- Always use your tools to gather facts before responding
- Check order details when customer mentions their order
- Check refund history before making any refund decisions
- Be empathetic but honest

Your personality:
- Friendly and professional
- Patient even when customer is angry
- Clear and concise in your replies
- No emojies

Important rules:
- Always check order details first before responding
- Never approve or deny a refund yourself
- If refund decision is needed — tell customer you are checking with your team
- Never use bold text, bullet points or any markdown formatting. Plain text only.
- Keep replies concise and conversational. Maximum 3-4 sentences. No long paragraphs.
"""


# SUPPORT TOOLS --> tool schema that ai will read and use to execute tasks. Each tool has a name, description, and parameters that the ai agent can use to perform specific actions.

SUPPORT_TOOLS = [
    {
        "name": "get_order_details",
        "description": "Fetch complete order details including status, carrier, tracking number and days since order was placed. Use this when customer mentions their order or complains about delivery.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "The order ID to look up"
                }
            },
            "required": ["order_id"]
        }
    },

    {
        "name": "get_refund_history",
        "description": "Get complete refund history for a user. Use this before making any refund related decisions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The user ID to check refund history for"
                }
            },
            "required": ["user_id"]
        }
    },

    {
        "name": "check_delivery_status",
        "description": "Check current delivery status using tracking number and carrier. Use this when customer complains about delayed or missing delivery.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tracking_number": {
                    "type": "string",
                    "description": "The shipment tracking number"
                },
                "carrier": {
                    "type": "string",
                    "description": "The carrier name for example BlueDart or Delhivery"
                }
            },
            "required": ["tracking_number", "carrier"]
        }
    },

    {
        "name": "escalate_to_manager",
        "description": "Escalate the case to manager for refund decision. Always include customer's user_id in the case summary so manager can assess fraud risk accurately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_summary": {
                    "type": "string",
                    "description": "Complete case summary. Must include: customer user_id, order details, refund history and complaint. Format: Start with 'Customer User ID: X' on the first line."
                }
            },
            "required": ["case_summary"]
        }
    },

    {
        "name": "search_knowledge_base",
        "description": "Search CoolBreeze AC company documents including refund policy, warranty policy, and product FAQs. Use this when customer asks about company policies, warranty coverage, warranty claims, refund eligibility, or any general product information that requires accurate company documentation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information from company documents. Be specific — for example 'refund eligibility within 30 days' instead of just 'refund'."
                }
            },
            "required": ["query"]
        }
    }

]


# EXECUTE_TOOLS -- > function that takes a tool name and input parameters, and executes the corresponding tool function. This allows the AI agent to perform specific actions based on user input and the tools available.
def execute_tool(tool_name, tool_input):
    if tool_name == "get_order_details":
        return get_order_details(tool_input["order_id"])

    if tool_name == "get_refund_history":
        return get_refund_history(tool_input["user_id"])

    if tool_name == "check_delivery_status":
        return check_delivery_status(tool_input["tracking_number"], tool_input["carrier"])

# AGENT LOOP --> while loop that continuously interacts with the user, processes their input, and executes tools as needed. The loop will continue until the user indicates they are done or the conversation is complete.


