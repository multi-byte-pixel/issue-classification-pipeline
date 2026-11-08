"""API Gateway HTTP API Lambda boundary with no AWS client created during import."""

import json
import logging
import os
from typing import Any

import boto3
from botocore.config import Config
from pydantic import ValidationError

from event_classifier.adapters import BedrockClassifierAdapter
from event_classifier.domain import ClassificationRequest
from event_classifier.service import ClassificationService

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def respond(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handle(event: dict[str, Any], service: ClassificationService) -> dict[str, Any]:
    """Validate at the edge; logging intentionally contains no conversation text.

    Authentication is enforced by API Gateway AWS_IAM, not by a token in the body.
    Provider unavailability is 503 with a valid NEEDS_REVIEW policy response;
    semantic uncertainty is 200 with NEEDS_REVIEW; bad input is a separate 400.
    """
    if event.get("routeKey") == "GET /health":
        return respond(200, {"status": "ok"})
    if event.get("routeKey") != "POST /v1/classifications":
        return respond(404, {"error": "not_found"})
    try:
        body = event.get("body")
        if not isinstance(body, str) or len(body.encode("utf-8")) > 64000:
            return respond(400, {"error": "invalid_request"})
        if event.get("isBase64Encoded", False):
            return respond(400, {"error": "base64_not_supported"})
        request = ClassificationRequest.model_validate_json(body)
    except ValidationError:
        # Validation exception messages can include raw input. Never log them here.
        return respond(400, {"error": "invalid_request"})
    result = service.classify(request)
    logger.info(
        json.dumps(
            {
                "request_id": result.request_id,
                "label": result.label,
                "fallback_reason": result.fallback_reason,
                "latency_ms": result.latency_ms,
                "model_id": result.model_id,
                "prompt_version": result.prompt_version,
            }
        )
    )
    status = 503 if result.fallback_reason in ("provider_timeout", "provider_error") else 200
    return respond(status, result.model_dump())


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Construct a bounded Bedrock client using the Lambda execution role."""
    client = boto3.client(
        "bedrock-runtime",
        config=Config(
            connect_timeout=2,
            read_timeout=8,
            retries={"total_max_attempts": 2, "mode": "standard"},
        ),
    )
    return handle(
        event,
        ClassificationService(BedrockClassifierAdapter(client, os.environ["BEDROCK_MODEL_ID"])),
    )
