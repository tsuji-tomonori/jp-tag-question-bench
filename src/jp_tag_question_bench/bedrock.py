"""Amazon Bedrock invocation helpers."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

RETRYABLE_CODES = {
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "ServiceUnavailableException",
    "ThrottlingException",
    "TooManyRequestsException",
}
_THREAD_LOCAL = threading.local()


@dataclass(frozen=True)
class InvocationResult:
    text: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    attempts: int


def extract_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()


def invoke(
    *,
    client: Any,
    model_id: str,
    prompt: str,
    temperature: float,
    max_tokens: int = 16,
    max_attempts: int = 6,
) -> InvocationResult:
    """Invoke one isolated Converse request with bounded exponential backoff."""
    started = time.perf_counter()
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )
            usage = response.get("usage", {})
            return InvocationResult(
                text=extract_text(response),
                latency_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=usage.get("inputTokens"),
                output_tokens=usage.get("outputTokens"),
                attempts=attempt,
            )
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in RETRYABLE_CODES or attempt == max_attempts:
                raise
        except BotoCoreError:
            if attempt == max_attempts:
                raise
        delay = min(30.0, 2 ** (attempt - 1)) + random.uniform(0.0, 0.5)
        time.sleep(delay)
    raise RuntimeError("unreachable")


def make_client(region: str) -> Any:
    """Return one Bedrock client per worker thread."""
    clients = getattr(_THREAD_LOCAL, "clients", None)
    if clients is None:
        clients = {}
        _THREAD_LOCAL.clients = clients
    if region not in clients:
        clients[region] = boto3.client("bedrock-runtime", region_name=region)
    return clients[region]
