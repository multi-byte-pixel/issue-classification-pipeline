"""Deterministic response policy around an untrusted provider."""

import time
import uuid

from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError
from pydantic import ValidationError

from event_classifier.adapters import Classifier
from event_classifier.domain import (
    ClassificationRequest,
    ClassificationResponse,
    ModelClassificationOutput,
    Reason,
)


class ClassificationService:
    def __init__(self, classifier: Classifier) -> None:
        self.classifier = classifier

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        """Keep known provider failures safe without swallowing programming bugs.

        Malformed model output becomes a deterministic review outcome. Invalid
        requests are rejected by the HTTP boundary before this method is called.
        TODO: add idempotency storage only when a reviewed use case requires it.
        """
        start = time.perf_counter()
        reason: Reason | None = None
        output = ModelClassificationOutput(label="NEEDS_REVIEW")
        try:
            raw = self.classifier.classify(request)
        except (TimeoutError, ReadTimeoutError):
            reason = "provider_timeout"
        except (BotoCoreError, ClientError):
            reason = "provider_error"
        else:
            try:
                output = ModelClassificationOutput.model_validate_json(raw)
            except ValidationError:
                reason = "invalid_model_output"
        if output.label == "NEEDS_REVIEW" and reason is None:
            reason = "ambiguous"
        return ClassificationResponse(
            request_id=str(uuid.uuid4()),
            conversation_id=request.conversation_id,
            label=output.label,
            requires_review=output.label == "NEEDS_REVIEW",
            fallback_reason=reason,
            model_id=self.classifier.model_id,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
