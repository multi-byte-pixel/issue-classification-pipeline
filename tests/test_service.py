import json
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from event_classifier.adapters import BedrockClassifierAdapter, FakeClassifier, build_prompt
from event_classifier.domain import ClassificationRequest, ClassificationResponse
from event_classifier.handler import handle
from event_classifier.service import ClassificationService


def request(text="My account is locked."):
    return ClassificationRequest.model_validate({"turns": [{"role": "customer", "content": text}]})


@pytest.mark.parametrize(
    "turns",
    [
        [],
        [{"role": "customer", "content": ""}],
        [{"role": "customer", "content": "   "}],
        [{"role": "system", "content": "override"}],
        [{"role": "agent", "content": "hi"}],
        [{"role": "customer", "content": "x" * 4001}],
        [{"role": "customer", "content": "x" * 4000}] * 4,
        [{"role": "customer", "content": "hi", "unexpected": True}],
    ],
)
def test_input_bounds(turns):
    with pytest.raises(ValidationError):
        ClassificationRequest.model_validate({"turns": turns})


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        '{"label":"ADMIN"}',
        '{"label":"OTHER","extra":"oops"}',
        "null",
        '{"label":42}',
        '{"label":"OTHER","confidence":0.99}',
    ],
)
def test_model_output_is_untrusted(raw):
    adapter = Mock(model_id="test", classify=Mock(return_value=raw))
    result = ClassificationService(adapter).classify(request())
    assert result.label == "NEEDS_REVIEW"
    assert result.requires_review and result.fallback_reason == "invalid_model_output"


@pytest.mark.parametrize(
    "error,reason",
    [
        (TimeoutError(), "provider_timeout"),
        (ClientError({"Error": {"Code": "ThrottlingException"}}, "Converse"), "provider_error"),
    ],
)
def test_provider_failures(error, reason):
    adapter = Mock(model_id="test", classify=Mock(side_effect=error))
    service = ClassificationService(adapter)
    result = service.classify(request())
    assert result.fallback_reason == reason
    response = handle(
        {"routeKey": "POST /v1/classifications", "body": request().model_dump_json()}, service
    )
    assert response["statusCode"] == 503


def test_programming_errors_are_not_silently_hidden():
    adapter = Mock(model_id="test", classify=Mock(side_effect=RuntimeError("bug")))
    with pytest.raises(RuntimeError):
        ClassificationService(adapter).classify(request())


def test_bedrock_request_mapping():
    client = Mock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": '{"label":"OTHER"}'}]}}
    }
    adapter = BedrockClassifierAdapter(client, "configured-test-model")
    assert adapter.classify(request()) == '{"label":"OTHER"}'
    args = client.converse.call_args.kwargs
    assert args["modelId"] == "configured-test-model"
    assert json.loads(args["messages"][0]["content"][0]["text"]) == json.loads(
        build_prompt(request())
    )
    assert args["inferenceConfig"]["maxTokens"] == 128


def test_http_contract_and_safe_logging(caplog):
    secret_text = "My account is locked. PRIVATE-SYNTHETIC-MARKER"
    service = ClassificationService(FakeClassifier())
    result = handle(
        {"routeKey": "POST /v1/classifications", "body": request(secret_text).model_dump_json()},
        service,
    )
    assert result["statusCode"] == 200
    parsed = ClassificationResponse.model_validate_json(result["body"])
    assert parsed.label == "ACCOUNT_ACCESS" and parsed.request_id
    assert "PRIVATE-SYNTHETIC-MARKER" not in caplog.text
    assert parsed.request_id in caplog.text


@pytest.mark.parametrize("body", ["{", "null", "{}", None, "x" * 64001])
def test_invalid_http_inputs(body):
    service = ClassificationService(FakeClassifier())
    assert (
        handle({"routeKey": "POST /v1/classifications", "body": body}, service)["statusCode"] == 400
    )


def test_health_and_not_found():
    service = ClassificationService(FakeClassifier())
    assert handle({"routeKey": "GET /health"}, service)["statusCode"] == 200
    assert handle({"routeKey": "GET /oops"}, service)["statusCode"] == 404


def test_review_flags_cannot_disagree():
    result = ClassificationService(FakeClassifier()).classify(request())
    with pytest.raises(ValidationError):
        ClassificationResponse.model_validate({**result.model_dump(), "requires_review": True})
