"""Transport layer; API failures stay visible rather than being dropped from metrics."""

import json
import time
import urllib.error
import urllib.request
from typing import Any, Protocol
from urllib.parse import urlsplit

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from event_classifier.domain import ClassificationRequest
from event_classifier.service import ClassificationService


class Runner(Protocol):
    def run(self, request: ClassificationRequest) -> tuple[int, Any, float]:
        """Return HTTP-equivalent status, untrusted decoded body, end-to-end latency."""
        ...


class LocalRunner:
    def __init__(self, service: ClassificationService) -> None:
        self.service = service

    def run(self, request: ClassificationRequest) -> tuple[int, Any, float]:
        start = time.perf_counter()
        result = self.service.classify(request)
        status = 503 if result.fallback_reason in ("provider_timeout", "provider_error") else 200
        return status, result.model_dump(), (time.perf_counter() - start) * 1000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        # Do not forward signed headers to redirects or unexpected destinations.
        return None


class ApiRunner:
    def __init__(self, target_url: str, region: str) -> None:
        parts = urlsplit(target_url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("target URL must be HTTPS, with no userinfo, query, or fragment")
        self.url = target_url.rstrip("/") + "/v1/classifications"
        self.region = region
        self.session = boto3.Session(region_name=region)
        self.opener = urllib.request.build_opener(NoRedirect())

    def run(self, request: ClassificationRequest) -> tuple[int, Any, float]:
        """Sign requests with short-lived AWS credentials; never retry scenario calls."""
        credentials = self.session.get_credentials()
        if credentials is None:
            raise ValueError("No AWS credentials for authenticated API evaluation")
        data = request.model_dump_json().encode()
        signed = AWSRequest(
            method="POST", url=self.url, data=data, headers={"Content-Type": "application/json"}
        )
        SigV4Auth(credentials.get_frozen_credentials(), "execute-api", self.region).add_auth(signed)
        outgoing = urllib.request.Request(self.url, data=data, headers=dict(signed.headers.items()))
        start = time.perf_counter()
        try:
            with self.opener.open(outgoing, timeout=40) as response:
                status, body = response.status, response.read(65537)
        except urllib.error.HTTPError as error:
            status, body = error.code, error.read(65537)
        except (urllib.error.URLError, TimeoutError):
            return 0, {"error": "transport_error"}, (time.perf_counter() - start) * 1000
        try:
            decoded: Any = json.loads(body) if len(body) <= 65536 else None
        except (ValueError, UnicodeDecodeError):
            decoded = None
        return int(status), decoded, (time.perf_counter() - start) * 1000
