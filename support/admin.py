from django.contrib import admin

from .models import AgentLog, Conversation, Message

# Register your models here.
admin.site.register(AgentLog)
admin.site.register(Conversation)
admin.site.register(Message)
