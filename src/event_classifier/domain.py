"""Contracts shared by the handler, service, adapters, and evaluation harness."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Label = Literal[
    "BILLING_ISSUE", "SERVICE_OUTAGE", "ACCOUNT_ACCESS", "POLICY_CHANGE", "OTHER", "NEEDS_REVIEW"
]
LABELS: tuple[str, ...] = (
    "BILLING_ISSUE",
    "SERVICE_OUTAGE",
    "ACCOUNT_ACCESS",
    "POLICY_CHANGE",
    "OTHER",
    "NEEDS_REVIEW",
)
Reason = Literal["provider_timeout", "provider_error", "invalid_model_output", "ambiguous"]
PROMPT_VERSION = "classification-v1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConversationTurn(Contract):
    role: Literal["customer", "agent"]
    content: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def nonblank(self) -> "ConversationTurn":
        if not self.content.strip():
            raise ValueError("blank conversation turn")
        return self


class ClassificationRequest(Contract):
    conversation_id: str | None = Field(default=None, max_length=128)
    turns: list[ConversationTurn] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def bounded_customer_context(self) -> "ClassificationRequest":
        if not any(turn.role == "customer" for turn in self.turns):
            raise ValueError("at least one customer turn is required")
        if sum(len(turn.content) for turn in self.turns) > 12000:
            raise ValueError("conversation exceeds total character budget")
        return self


class ModelClassificationOutput(Contract):
    # Confidence is deliberately omitted: self-reported confidence is not calibrated.
    label: Label


class ClassificationResponse(Contract):
    request_id: str = Field(min_length=1)
    conversation_id: str | None
    label: Label
    requires_review: bool
    fallback_reason: Reason | None
    model_id: str
    prompt_version: str = PROMPT_VERSION
    latency_ms: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def consistent_review_policy(self) -> "ClassificationResponse":
        review = self.label == "NEEDS_REVIEW"
        if self.requires_review != review or (self.fallback_reason is not None) != review:
            raise ValueError("review label, flag, and reason must agree")
        return self
