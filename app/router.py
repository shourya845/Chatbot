"""Small deterministic router for the four primary chatbot intents."""
import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    DEMO = "demo"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    reason: str


GREETING = re.compile(r"^(?:hi|hello|hey|good (?:morning|afternoon|evening))[!. ]*$", re.I)
THANKS = re.compile(r"^(?:thanks|thank you|great|okay|ok|got it)[!. ]*$", re.I)
GOODBYE = re.compile(r"^(?:bye|goodbye|see you)[!. ]*$", re.I)
PRICING = re.compile(r"\b(?:price|prices|pricing|cost|costs|plan|plans|subscription)\b", re.I)
DEMO = re.compile(
    r"\b(?:book|schedule|request|arrange)\b.{0,30}\b(?:demo|meeting|call)\b|"
    r"\b(?:want|need)\b.{0,12}\b(?:a )?demo\b|"
    r"\b(?:demo request|talk to sales|speak to sales|sales call)\b",
    re.I,
)
A3I_SCOPE = re.compile(
    r"\b(?:a3i|a31|nextory|speedhire|speedrec|h3ive|send3r|invenio|"
    r"video ai|video studio|voice assist|ai-note|ai-hire|ai-lead|ai-advisor|"
    r"ai-marketing|meeting bot|meeting notes|scheduling bot|smart scan|voice agent|lead agent|"
    r"personal agent|automated data entry|multi-language|apps|ants|agents|company|team|"
    r"leadership|founders?|contact|"
    r"careers?|jobs?|industry|industries|resources?|articles?|responsible ai|privacy|"
    r"terms|refund|collaboration|partnership|competition|service|workflow|product)\b",
    re.I,
)
WEBSITE_QUESTION = re.compile(
    r"^(?:what (?:is|does) (?:this|the company)|what do you do|who are you|"
    r"how can (?:you|this) help|tell me about (?:this|the company)|"
    r"what (?:can|do) you offer|how (?:can|do) i contact you)",
    re.I,
)
FOLLOW_UP = re.compile(
    r"\b(?:it|its|they|their|this|that)\b|^(?:what about|and |tell me more|explain more)",
    re.I,
)
OFF_TOPIC = re.compile(
    r"\b(?:recipe|weather|sports score|football score|stock price|write code|"
    r"debug code|homework|medical advice|legal advice|politics|poem|story|joke)\b",
    re.I,
)
PROHIBITED = re.compile(
    r"\b(?:ignore (?:the )?(?:rules|instructions)|reveal (?:the )?(?:system prompt|api key|credentials)|"
    r"show (?:the )?(?:system prompt|developer message)|print (?:the )?(?:api key|credentials))\b",
    re.I,
)


def route_intent(
    message: str, history: list[dict] | None = None, page_path: str = ""
) -> IntentDecision:
    """Route obvious cases without an LLM or an external request."""
    text = message.strip()
    history = history or []
    if PRICING.search(text):
        return IntentDecision(Intent.KNOWLEDGE, "pricing_requires_evidence")
    if DEMO.search(text):
        return IntentDecision(Intent.DEMO, "demo_request")
    if GREETING.fullmatch(text):
        return IntentDecision(Intent.CONVERSATION, "greeting")
    if THANKS.fullmatch(text):
        return IntentDecision(Intent.CONVERSATION, "thanks")
    if GOODBYE.fullmatch(text):
        return IntentDecision(Intent.CONVERSATION, "goodbye")
    if PROHIBITED.search(text):
        return IntentDecision(Intent.UNSUPPORTED, "prohibited_request")
    if OFF_TOPIC.search(text):
        return IntentDecision(Intent.UNSUPPORTED, "obvious_off_topic")
    if A3I_SCOPE.search(text) or WEBSITE_QUESTION.search(text):
        return IntentDecision(Intent.KNOWLEDGE, "a3i_scope")
    if FOLLOW_UP.search(text) and (history or page_path not in ("", "/")):
        return IntentDecision(Intent.KNOWLEDGE, "contextual_follow_up")
    if re.fullmatch(r"(?:what is this|what about it|tell me more)[?!. ]*", text, re.I):
        return IntentDecision(Intent.CONVERSATION, "clarification_needed")
    return IntentDecision(Intent.UNSUPPORTED, "outside_a3i_scope")
