import json
import urllib.error
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.credentials import Credentials

from evaluation.runners import ApiRunner, NoRedirect
from event_classifier.domain import ClassificationRequest


def request():
    return ClassificationRequest.model_validate(
        {"turns": [{"role": "customer", "content": "My account is locked."}]}
    )


def api():
    session = Mock()
    # Synthetic credentials used only to test signing; no request is sent.
    session.get_credentials.return_value = Credentials("synthetic-key", "synthetic-secret")
    with patch("evaluation.runners.boto3.Session", return_value=session):
        result = ApiRunner("https://example.test", "us-east-1")
    result.opener = MagicMock()
    return result


def test_sigv4_request_contract():
    runner = api()
    response = runner.opener.open.return_value.__enter__.return_value = Mock()
    response.status = 200
    response.read.return_value = b'{"label":"ACCOUNT_ACCESS"}'
    status, body, latency = runner.run(request())
    assert status == 200 and body["label"] == "ACCOUNT_ACCESS" and latency >= 0
    outgoing = runner.opener.open.call_args.args[0]
    assert outgoing.get_header("Authorization").startswith("AWS4-HMAC-SHA256 ")
    assert json.loads(outgoing.data)["turns"][0]["content"] == "My account is locked."
    assert outgoing.full_url == "https://example.test/v1/classifications"


@pytest.mark.parametrize("body", [b"not json", b"x" * 65537])
def test_bad_api_json_is_exposed_to_contract_evaluator(body):
    runner = api()
    response = runner.opener.open.return_value.__enter__.return_value = Mock()
    response.status = 200
    response.read.return_value = body
    assert runner.run(request())[:2] == (200, None)


def test_transport_failure_preserves_attempt():
    runner = api()
    runner.opener.open.side_effect = urllib.error.URLError("synthetic timeout")
    assert runner.run(request())[:2] == (0, {"error": "transport_error"})


def test_no_credentials_fails_loudly():
    runner = api()
    runner.session.get_credentials.return_value = None
    with pytest.raises(ValueError):
        runner.run(request())


def test_redirect_cannot_forward_signed_headers():
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test") is None
