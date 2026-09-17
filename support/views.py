import json
import traceback

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from orders.models import Order

from .agents import run_support_agent
from .models import Conversation, Message


@login_required
def chat(request, order_id):

    # Only allow POST
    if request.method != "POST":

        return JsonResponse(
            {
                "error": "POST request required"
            },
            status=405,
        )


    try:

        # ---------------------------------------------
        # READ JSON REQUEST
        # ---------------------------------------------

        data = json.loads(request.body)

        user_message = data.get(
            "message",
            ""
        ).strip()


        # ---------------------------------------------
        # VALIDATE MESSAGE
        # ---------------------------------------------

        if not user_message:

            return JsonResponse(
                {
                    "error": "Empty message"
                },
                status=400,
            )


        # ---------------------------------------------
        # GET ORDER
        # ---------------------------------------------

        order = get_object_or_404(

            Order,

            id=order_id,

            user=request.user,
        )


        # ---------------------------------------------
        # GET OR CREATE CONVERSATION
        # ---------------------------------------------

        conversation, created = (
            Conversation.objects.get_or_create(

                user=request.user,

                order=order,
            )
        )


        # ---------------------------------------------
        # SAVE USER MESSAGE
        # ---------------------------------------------

        Message.objects.create(

            conversation=conversation,

            role="user",

            content=user_message,
        )


        print("\n======================================")
        print("NEW CHAT MESSAGE")
        print("======================================")

        print("User:", request.user)
        print("Order:", order.id)
        print("Conversation:", conversation.id)
        print("Message:", user_message)


        # ---------------------------------------------
        # RUN SUPPORT AGENT
        # ---------------------------------------------

        reply = run_support_agent(

            user_message=user_message,

            conversation_id=conversation.id,

            order_id=order.id,

            user_id=request.user.id,
        )


        # ---------------------------------------------
        # SAVE AI RESPONSE
        # ---------------------------------------------

        Message.objects.create(

            conversation=conversation,

            role="assistant",

            content=reply,
        )


        # ---------------------------------------------
        # SEND RESPONSE TO FRONTEND
        # ---------------------------------------------

        return JsonResponse(
            {
                "reply": reply
            }
        )


    except json.JSONDecodeError:

        return JsonResponse(
            {
                "error": "Invalid JSON request"
            },
            status=400,
        )


    except Exception as error:

        print("\n")
        print("!!!!!!!! CHAT ERROR !!!!!!!!")

        print(
            type(error).__name__,
            ":",
            error,
        )

        traceback.print_exc()

        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("\n")


        return JsonResponse(
            {
                "error": str(error)
            },
            status=500,
        )


    
