"""Signed health check after an explicitly approved deployment; no inference."""

import json
import os
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from evaluation.runners import NoRedirect

session = boto3.Session()
credentials = session.get_credentials()
if credentials is None:
    raise SystemExit("AWS credentials required")
url = os.environ["API_URL"].rstrip("/") + "/health"
request = AWSRequest(method="GET", url=url)
SigV4Auth(credentials.get_frozen_credentials(), "execute-api", os.environ["AWS_REGION"]).add_auth(
    request
)
opener = urllib.request.build_opener(NoRedirect())
with opener.open(
    urllib.request.Request(url, headers=dict(request.headers.items())), timeout=15
) as response:
    if response.status != 200 or json.load(response) != {"status": "ok"}:
        raise SystemExit("Post-deployment health check failed")
