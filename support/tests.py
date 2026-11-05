"""
Tests for the risk profile tool, the refund guardrails and the multi-agent
wiring (Aura -> Manager -> Risk Agent).

The agent tests use a scripted fake Claude client, so they run offline,
cost nothing and always behave the same. Run with:

    python manage.py test support
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase

from orders.models import Order, RefundRequest
from support import agents
from support.fraud_test_data import (
    DemoDataError,
    remove_fraud_test_data,
    seed_fraud_test_data,
)
from support.models import AgentLog, Conversation, Message
from support.tools import get_customer_risk_profile, record_refund_decision


def live_case(username):
    """The most recent order of a demo customer (the one to chat about)."""
    return Order.objects.filter(user__username=username).latest("created_at")


# ---------------------------------------------------------
# RISK PROFILE TOOL
# ---------------------------------------------------------

class RiskProfileTests(TestCase):
    fixtures = ["demo_data"]

    def setUp(self):
        self.summary = seed_fraud_test_data()

    def profile(self, username):
        return get_customer_risk_profile(User.objects.get(username=username).id)

    def test_demo_customers_get_expected_levels(self):
        for row in self.summary:
            with self.subTest(customer=row["username"]):
                self.assertEqual(
                    self.profile(row["username"])["rule_based_level"],
                    row["expected_risk"],
                )

    def test_high_risk_customer_has_explainable_flags(self):
        codes = {flag["code"] for flag in self.profile("marco")["flags"]}
        self.assertIn("refund_burst", codes)
        self.assertIn("repeated_not_received_on_delivered", codes)
        self.assertIn("empty_box_claims", codes)
        self.assertIn("many_delivery_addresses", codes)

    def test_loyal_customer_has_no_flags(self):
        profile = self.profile("nina")
        self.assertEqual(profile["flags"], [])
        self.assertEqual(profile["refund_requests"]["total"], 1)

    def test_existing_demo_customers(self):
        self.assertEqual(self.profile("lexi")["rule_based_level"], "medium")
        self.assertEqual(self.profile("Elias")["rule_based_level"], "low")

    def test_unknown_customer(self):
        self.assertIn("error", get_customer_risk_profile(999999))

    def test_seeding_twice_replaces_the_demo_data(self):
        seed_fraud_test_data()
        self.assertEqual(User.objects.filter(username="marco").count(), 1)
        self.assertEqual(Order.objects.filter(user__username="marco").count(), 5)

    def test_seeding_refuses_to_touch_real_accounts(self):
        remove_fraud_test_data()
        User.objects.create_user("nina", email="nina@realmail.eu", password="x")
        with self.assertRaises(DemoDataError):
            seed_fraud_test_data()
        self.assertEqual(User.objects.get(username="nina").email, "nina@realmail.eu")


# ---------------------------------------------------------
# REFUND GUARDRAILS (enforced in code, not by the model)
# ---------------------------------------------------------

class RefundGuardrailTests(TestCase):
    fixtures = ["demo_data"]

    def setUp(self):
        seed_fraud_test_data()
        self.order = live_case("nina")  # 449.00 EUR, no refund yet

    def test_low_risk_approval_is_approved(self):
        result = record_refund_decision(self.order, "approve", "Damaged", 1000, risk_level="low")
        self.assertEqual(result["status"], "Approved")

    def test_high_risk_approval_goes_to_human_staff(self):
        result = record_refund_decision(self.order, "approve", "Damaged", 1000, risk_level="high")
        self.assertEqual(result["status"], "Pending")
        self.assertIn("risk level is high", result["note"])

    def test_high_risk_never_turns_a_denial_into_anything_else(self):
        result = record_refund_decision(self.order, "deny", "Too late", 1000, risk_level="high")
        self.assertEqual(result["status"], "Denied")

    def test_amount_over_limit_goes_to_human_staff(self):
        result = record_refund_decision(self.order, "approve", "Damaged", 100, risk_level="low")
        self.assertEqual(result["status"], "Pending")
        self.assertIn("approval limit", result["note"])

    def test_internal_note_is_not_shown_to_the_customer(self):
        record_refund_decision(
            self.order, "refer", "High risk: repeated claims (internal)", 1000,
            risk_level="high", customer_claim="TV arrived with a cracked screen",
        )
        refund = RefundRequest.objects.get(order=self.order)
        self.assertEqual(refund.reason, "TV arrived with a cracked screen")
        self.assertEqual(refund.decision_note, "High risk: repeated claims (internal)")

        client = Client()
        client.force_login(self.order.user)
        page = client.get(f"/orders/{self.order.id}/").content.decode()
        self.assertIn("TV arrived with a cracked screen", page)
        self.assertNotIn("repeated claims", page)
        self.assertNotIn("High risk", page)


# ---------------------------------------------------------
# FINAL RISK ASSESSMENT (agent output combined with rules)
# ---------------------------------------------------------

class FinalizeRiskAssessmentTests(SimpleTestCase):
    HIGH_PROFILE = {
        "rule_based_level": "high",
        "flags": [{"code": "refund_burst", "severity": "high", "detail": "4 refunds in 30 days"}],
    }
    LOW_PROFILE = {"rule_based_level": "low", "flags": []}

    def test_agent_cannot_lower_the_rule_based_level(self):
        result = agents.finalize_risk_assessment(
            {"risk_level": "low", "risk_score": 10, "key_signals": [], "recommendation": "proceed"},
            self.HIGH_PROFILE,
        )
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["recommendation"], "refer_to_human")
        self.assertGreaterEqual(result["risk_score"], 70)
        self.assertIn("4 refunds in 30 days", result["key_signals"])

    def test_agent_can_raise_the_level(self):
        result = agents.finalize_risk_assessment(
            {"risk_level": "medium", "risk_score": 45, "key_signals": ["x"],
             "recommendation": "proceed_with_caution"},
            self.LOW_PROFILE,
        )
        self.assertEqual(result["risk_level"], "medium")
        self.assertEqual(result["risk_score"], 45)

    def test_score_is_kept_inside_the_level_band(self):
        result = agents.finalize_risk_assessment(
            {"risk_level": "high", "risk_score": 20, "key_signals": [], "recommendation": "refer_to_human"},
            self.LOW_PROFILE,
        )
        self.assertEqual(result["risk_score"], 70)

    def test_recommendation_is_never_weaker_than_the_level(self):
        result = agents.finalize_risk_assessment(
            {"risk_level": "medium", "risk_score": 50, "key_signals": [], "recommendation": "proceed"},
            self.LOW_PROFILE,
        )
        self.assertEqual(result["recommendation"], "proceed_with_caution")

    def test_missing_submission_falls_back_to_rules(self):
        result = agents.finalize_risk_assessment({}, self.HIGH_PROFILE)
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["source"], "rules")


# ---------------------------------------------------------
# MULTI-AGENT WIRING WITH A SCRIPTED FAKE CLAUDE
# ---------------------------------------------------------

def tool_use(name, tool_input, block_id):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)],
    )


def text(reply):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=reply)])


class FakeClaude:
    """Returns scripted responses in order and records which agent asked."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        system = kwargs["system"]
        if system.startswith(agents.RISK_SYSTEM_PROMPT):
            agent = "Risk"
        elif system.startswith(agents.MANAGER_SYSTEM_PROMPT):
            agent = "Manager"
        else:
            agent = "Aura"
        self.calls.append((agent, [tool["name"] for tool in kwargs["tools"]]))
        return self.responses.pop(0)


class MultiAgentWiringTests(TestCase):
    fixtures = ["demo_data"]

    def setUp(self):
        seed_fraud_test_data()

    def start_chat(self, username, text_from_customer):
        order = live_case(username)
        conversation = Conversation.objects.create(user=order.user, order=order)
        Message.objects.create(conversation=conversation, role="user", content=text_from_customer)
        return order, conversation

    def test_aura_manager_and_risk_agent_hand_off_in_order(self):
        order, conversation = self.start_chat("marco", "My phone never arrived. Refund me.")

        fake = FakeClaude([
            tool_use("escalate_to_manager", {"request_type": "refund", "summary": "Says phone never arrived"}, "t1"),
            tool_use("request_risk_assessment", {"case_summary": "Not received claim"}, "t2"),
            tool_use("get_customer_risk_profile", {}, "t3"),
            # The model under-rates the risk: the rule-based floor must correct it
            tool_use("submit_risk_assessment", {"risk_score": 20, "risk_level": "low",
                                                "key_signals": [], "recommendation": "proceed",
                                                "summary": "Looks fine"}, "t4"),
            text("Assessment submitted."),
            tool_use("record_refund_decision", {"decision": "approve", "customer_claim": "Phone not received",
                                                "reason": "Not delivered"}, "t5"),
            text("Decision: referred to a specialist."),
            text("A specialist will review your case and get back to you."),
        ])

        with mock.patch.object(agents, "client", fake):
            reply = agents.run_support_agent(
                "My phone never arrived. Refund me.", conversation.id, order.id, order.user_id,
            )

        self.assertEqual(reply, "A specialist will review your case and get back to you.")
        self.assertEqual(
            [agent for agent, _ in fake.calls],
            ["Aura", "Manager", "Risk", "Risk", "Risk", "Manager", "Manager", "Aura"],
        )
        self.assertIn("escalate_to_manager", fake.calls[0][1])
        self.assertIn("request_risk_assessment", fake.calls[1][1])
        self.assertIn("submit_risk_assessment", fake.calls[2][1])
        self.assertNotIn("request_risk_assessment", fake.calls[0][1])  # Aura cannot call Risk directly

        refund = RefundRequest.objects.get(order=order)
        self.assertEqual(refund.status, "pending")  # approved by the model, held for humans by code

        risk_logs = AgentLog.objects.filter(conversation=conversation, event_type=AgentLog.EventType.RISK)
        self.assertTrue(risk_logs.filter(message__contains="level=high").exists())

    def test_guardrail_applies_even_if_manager_skips_the_risk_agent(self):
        order, conversation = self.start_chat("marco", "Refund please.")

        fake = FakeClaude([
            tool_use("record_refund_decision", {"decision": "approve", "customer_claim": "Phone not received",
                                                "reason": "Not delivered"}, "t1"),
            text("Approved."),
        ])
        with mock.patch.object(agents, "client", fake):
            agents.run_manager_agent(conversation, "refund", "Says phone never arrived")

        self.assertEqual(RefundRequest.objects.get(order=order).status, "pending")

    def test_low_risk_customer_is_approved(self):
        order, conversation = self.start_chat("nina", "My TV arrived with a cracked screen.")

        fake = FakeClaude([
            tool_use("request_risk_assessment", {"case_summary": "Cracked screen on arrival"}, "t1"),
            tool_use("submit_risk_assessment", {"risk_score": 8, "risk_level": "low", "key_signals": [],
                                                "recommendation": "proceed", "summary": "Loyal customer"}, "t2"),
            text("Done."),
            tool_use("record_refund_decision", {"decision": "approve", "customer_claim": "TV arrived cracked",
                                                "reason": "Arrived damaged"}, "t3"),
            text("Approved."),
        ])
        with mock.patch.object(agents, "client", fake):
            agents.run_manager_agent(conversation, "damaged_product", "TV arrived with cracked screen")

        self.assertEqual(RefundRequest.objects.get(order=order).status, "approved")

    def test_manager_is_reminded_to_record_a_decision_it_only_described(self):
        order, conversation = self.start_chat("nina", "My TV arrived with a cracked screen.")

        fake = FakeClaude([
            text("Decision: Approve."),  # described, but no tool call
            tool_use("record_refund_decision", {"decision": "approve", "customer_claim": "TV arrived cracked",
                                                "reason": "Arrived damaged"}, "t1"),
            text("Approved."),
        ])
        with mock.patch.object(agents, "client", fake):
            reply = agents.run_manager_agent(conversation, "damaged_product", "TV arrived cracked")

        self.assertEqual(RefundRequest.objects.get(order=order).status, "approved")
        self.assertEqual(reply, "Approved.")
        self.assertEqual(len(fake.calls), 3)

    def test_aura_is_told_the_real_outcome_when_nothing_is_recorded(self):
        order, conversation = self.start_chat("nina", "My TV arrived with a cracked screen.")

        fake = FakeClaude([text("Decision: Approve."), text("Approve, as I said.")])
        with mock.patch.object(agents, "client", fake):
            reply = agents.run_manager_agent(conversation, "damaged_product", "TV arrived cracked")

        refund = RefundRequest.objects.get(order=order)
        self.assertEqual(refund.status, "pending")
        self.assertEqual(refund.reason, "Damaged product claim")
        self.assertIn("referred to a specialist", reply)
        self.assertNotIn("Approve", reply)
