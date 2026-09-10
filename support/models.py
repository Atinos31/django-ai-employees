from django.conf import settings
from django.db import models


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="support_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Conversation #{self.pk} - "
            f"{self.user.username} - Order #{self.order_id}"
        )


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        AGENT = "agent", "Agent"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:50]}"


class AgentLog(models.Model):
    class EventType(models.TextChoices):
        SUPPORT = "support", "Support Agent"
        TOOL_CALL = "tool_call", "Tool Call"
        TOOL_RESULT = "tool_result", "Tool Result"
        MANAGER = "manager", "Manager Agent"
        RISK = "risk", "Risk Agent"
        FINAL = "final", "Final Reply"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="agent_logs",
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.get_event_type_display()}] {self.message[:40]}"