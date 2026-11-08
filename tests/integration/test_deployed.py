"""No credentials or paid calls unless explicitly opted into by the operator."""

import os

import pytest

from evaluation.runners import ApiRunner
from event_classifier.domain import ClassificationRequest, ClassificationResponse

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ALLOW_CLOUD_TESTS") != "true",
        reason="Live AWS/Bedrock execution requires explicit authorization",
    ),
]


def test_authenticated_multiturn():
    runner = ApiRunner(os.environ["API_URL"], os.environ["AWS_REGION"])
    request = ClassificationRequest.model_validate(
        {
            "turns": [
                {"role": "customer", "content": "Something seems wrong."},
                {"role": "agent", "content": "What is happening?"},
                {"role": "customer", "content": "My account is locked."},
            ]
        }
    )
    status, body, _ = runner.run(request)
    assert status == 200
    result = ClassificationResponse.model_validate(body)
    assert result.label == "ACCOUNT_ACCESS"
