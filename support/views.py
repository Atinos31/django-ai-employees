from django.shortcuts import render, get_object_or_404
import json
from django.http import JsonResponse, StreamingHttpResponse


# Create your views here.

def chat(request, order_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        user_message = data.get("message")
        # print(user_message)

        if not user_message:
                return JsonResponse({"error": "Empty message"}, status=400)
        return JsonResponse({"reply": "here is the reply"})
        


    
