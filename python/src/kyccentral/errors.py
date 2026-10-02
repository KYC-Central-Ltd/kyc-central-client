"""Exception hierarchy for the KYC Central client.

Every error raised by this library inherits from :class:`KYCCentralError`, so a
single ``except KYCCentralError`` catches transport failures and API errors
alike. Callers that care about the difference can catch the narrower types.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "APIConnectionError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "JobError",
    "JobFailedError",
    "JobTimeoutError",
    "KYCCentralError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "ServiceUnavailableError",
    "UnprocessableEntityError",
    "status_error_from_response",
]


class KYCCentralError(Exception):
    """Base class for every error raised by this library."""


class APIConnectionError(KYCCentralError):
    """The request never produced a response (DNS, TLS, connection reset, …)."""

    def __init__(self, message: str = "Could not reach the KYC Central API.") -> None:
        super().__init__(message)


class APITimeoutError(APIConnectionError):
    """The request timed out before the API responded."""

    def __init__(self, message: str = "Request to the KYC Central API timed out.") -> None:
        super().__init__(message)


class APIStatusError(KYCCentralError):
    """The API returned a non-2xx status.

    Attributes:
        status_code: HTTP status code returned by the API.
        detail: Human-readable message from the API's ``{"detail": ...}`` body,
            falling back to the raw response text.
        body: The decoded response body, when it was JSON.
        headers: Response headers, useful for rate-limit introspection. Lookups
            are case-insensitive, as HTTP header names are.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        detail: str | None = None,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.body = body
        # Kept as the transport's own header mapping rather than copied into a
        # plain dict: that mapping is case-insensitive, so both `Retry-After`
        # and `retry-after` resolve, which a dict copy would silently break.
        self.headers: Mapping[str, str] = headers if headers is not None else {}


class BadRequestError(APIStatusError):
    """400 — the request was malformed."""


class AuthenticationError(APIStatusError):
    """401 — no API key was sent, or the key is not valid.

    Most endpoints work anonymously at a reduced rate limit, but
    ``client.kyc.assess()`` and the AI endpoints always require a key.
    """


class PermissionDeniedError(APIStatusError):
    """403 — the key is valid but the plan does not include this endpoint.

    In practice this almost always means an active Professional subscription is
    required, or that an existing subscription is past due or cancelled. The
    :attr:`~APIStatusError.detail` message says which.
    """


class NotFoundError(APIStatusError):
    """404 — no such company, officer, charge or filing."""


class UnprocessableEntityError(APIStatusError):
    """422 — the request failed the API's validation rules.

    :attr:`~APIStatusError.body` holds FastAPI's structured validation errors.
    """


class RateLimitError(APIStatusError):
    """429 — the caller exceeded a rate limit or a plan quota.

    Attributes:
        retry_after: Seconds to wait before retrying, taken from the
            ``Retry-After`` response header when the API sends one.
    """

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(APIStatusError):
    """5xx — the API failed to handle an otherwise valid request."""


class ServiceUnavailableError(ServerError):
    """503 — a dependency the API needs is temporarily unavailable.

    Attributes:
        retry_after: Seconds to wait before retrying, taken from the
            ``Retry-After`` response header when the API sends one.
    """

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class JobError(KYCCentralError):
    """A background job the client was waiting on did not produce a result.

    The API queues expensive assessments rather than holding the connection open;
    this client polls the job to completion for you. These errors surface when
    that polling cannot deliver a result.
    """

    def __init__(self, message: str, *, job_id: str | None = None) -> None:
        super().__init__(message)
        self.job_id = job_id


class JobFailedError(JobError):
    """The API reported the queued assessment as failed."""


class JobTimeoutError(JobError):
    """The queued assessment did not finish within ``poll_timeout`` seconds.

    The job may still complete server-side. Re-issuing the same request will
    usually return the cached result once it does.
    """


_STATUS_MAP: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    422: UnprocessableEntityError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}


def _extract_detail(body: Any, fallback: str) -> str:
    """Pull the human-readable message out of an API error body.

    The API returns ``{"detail": "..."}`` for handled errors and FastAPI's
    ``{"detail": [{...}, ...]}`` list form for validation failures.
    """
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list) and detail:
            parts = []
            for item in detail:
                if isinstance(item, dict):
                    loc = ".".join(str(p) for p in item.get("loc", []) if p != "body")
                    msg = item.get("msg", "invalid value")
                    parts.append(f"{loc}: {msg}" if loc else str(msg))
                else:
                    parts.append(str(item))
            return "; ".join(parts)
    return fallback


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    """The ``Retry-After`` header as numeric seconds, or ``None`` when absent."""
    raw_retry = headers.get("Retry-After") or headers.get("retry-after")
    if raw_retry:
        try:
            return float(raw_retry)
        except ValueError:
            return None
    return None


def status_error_from_response(
    status_code: int,
    body: Any,
    headers: Mapping[str, str],
    *,
    method: str,
    url: str,
) -> APIStatusError:
    """Build the most specific :class:`APIStatusError` for a failed response."""
    detail = _extract_detail(body, f"HTTP {status_code}")
    message = f"{method} {url} failed with {status_code}: {detail}"

    if status_code in (429, 503):
        retry_cls = RateLimitError if status_code == 429 else ServiceUnavailableError
        return retry_cls(
            message,
            retry_after=_parse_retry_after(headers),
            status_code=status_code,
            detail=detail,
            body=body,
            headers=headers,
        )

    error_cls = _STATUS_MAP.get(status_code)
    if error_cls is None:
        error_cls = ServerError if status_code >= 500 else APIStatusError

    return error_cls(
        message,
        status_code=status_code,
        detail=detail,
        body=body,
        headers=headers,
    )
