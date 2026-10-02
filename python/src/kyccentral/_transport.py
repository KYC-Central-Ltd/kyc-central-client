"""HTTP plumbing shared by the sync and async clients.

Everything here is internal: the public surface is :mod:`kyccentral.client` and
:mod:`kyccentral.errors`. Kept in one module so that retry policy, error mapping
and header construction cannot drift between the two client flavours.
"""

from __future__ import annotations

import asyncio
import os
import platform
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from ._version import __version__
from .errors import APIConnectionError, APITimeoutError, status_error_from_response

DEFAULT_BASE_URL = "https://api.kyccentral.co.uk"
"""Production API. Override with ``base_url=`` or ``KYCCENTRAL_BASE_URL``."""

API_PREFIX = "/v1"
"""Every business endpoint is versioned. ``/health`` deliberately is not."""

DEFAULT_TIMEOUT = 30.0
AI_TIMEOUT = 120.0
"""Default timeout (seconds) for the LLM-backed endpoints, which routinely outlast
:data:`DEFAULT_TIMEOUT`. A client configured with a longer timeout keeps it."""
DEFAULT_MAX_RETRIES = 2

_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_INITIAL_BACKOFF = 0.5
_MAX_BACKOFF = 8.0

API_KEY_ENV = "KYCCENTRAL_API_KEY"
BASE_URL_ENV = "KYCCENTRAL_BASE_URL"


def _default_user_agent() -> str:
    return (
        f"kyccentral-python/{__version__} "
        f"(httpx/{httpx.__version__}; python/{platform.python_version()})"
    )


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop unset query parameters.

    ``None`` means "caller did not supply this", which must not be sent as the
    literal string ``None``. Empty sequences are dropped too: the API's
    repeatable parameters (``confirmed_media_url``, …) default to empty anyway,
    and sending nothing keeps URLs short.
    """
    if not params:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            values = [v for v in value if v is not None]
            if not values:
                continue
            cleaned[key] = values
        else:
            cleaned[key] = value
    return cleaned


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse the ``Retry-After`` header as a numeric seconds value.

    Returns the value if present and numeric, None otherwise. A numeric
    Retry-After greater than the max backoff will not be waited out: the
    response is surfaced to the caller immediately so they can schedule
    the retry themselves.
    """
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return None


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    """Seconds to wait before the next attempt.

    Honours ``Retry-After`` when the API sends one (it does on 429), otherwise
    backs off exponentially with full jitter so that a fleet of clients recovering
    from the same outage does not retry in lockstep. A Retry-After value greater
    than the max backoff will not be waited out — the response is surfaced to the
    caller with retry_after set, so they can schedule the retry themselves.
    """
    if response is not None:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, _MAX_BACKOFF)
    ceiling = min(_INITIAL_BACKOFF * (2**attempt), _MAX_BACKOFF)
    return random.uniform(ceiling / 2, ceiling)


def _resolve_ai_timeout(client_timeout: float, timeout: float | None) -> float:
    """Effective timeout for an AI call: the per-call value, else ``max(client, AI)``."""
    if timeout is not None:
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        return timeout
    return max(client_timeout, AI_TIMEOUT)


def _decode(response: httpx.Response) -> Any:
    """Decode a response body, tolerating empty and non-JSON payloads."""
    if response.status_code == 204 or not response.content:
        return None
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return response.json()
        except ValueError:
            return response.text
    return response.text


@dataclass(frozen=True)
class ClientConfig:
    """Resolved connection settings shared by a client and its resources."""

    api_key: str | None
    base_url: str
    timeout: float
    max_retries: int
    default_headers: Mapping[str, str]

    @classmethod
    def resolve(
        cls,
        api_key: str | None,
        base_url: str | None,
        timeout: float,
        max_retries: int,
        default_headers: Mapping[str, str] | None,
    ) -> ClientConfig:
        raw_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
        # A blank key (explicit or from the environment) means "no key"; an explicit
        # empty string does not fall back to the environment variable.
        resolved_key = raw_key if raw_key is not None and raw_key.strip() else None
        resolved_base = base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        return cls(
            api_key=resolved_key,
            base_url=resolved_base.rstrip("/"),
            timeout=timeout,
            max_retries=max_retries,
            default_headers=dict(default_headers or {}),
        )

    def url_for(self, path: str, versioned: bool = True) -> str:
        prefix = API_PREFIX if versioned else ""
        return f"{self.base_url}{prefix}/{path.lstrip('/')}"

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": _default_user_agent(),
        }
        headers.update(self.default_headers)
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers


class _BaseTransport:
    """Shared retry bookkeeping. Subclasses supply the actual I/O."""

    def __init__(self, config: ClientConfig) -> None:
        self._config = config

    @property
    def config(self) -> ClientConfig:
        return self._config

    def _should_retry(
        self,
        method: str,
        attempt: int,
        response: httpx.Response | None = None,
        exc: Exception | None = None,
    ) -> bool:
        """Whether a failed attempt may be repeated.

        GETs retry timeouts, transport errors and retryable statuses. A POST may be
        a billed LLM call that is still running server-side, so it is repeated only
        when it certainly never reached the server (the connection could not be
        established, and it was not a timeout) or when a 429/503 carries
        ``Retry-After`` (the server is saying "not processed, come back later").

        If a response has a Retry-After greater than the max backoff, it is not
        retried — the error is surfaced immediately so the caller can schedule the
        retry themselves.
        """
        if attempt >= self._config.max_retries:
            return False
        is_get = method.upper() == "GET"
        if response is not None:
            if response.status_code not in _RETRYABLE_STATUSES:
                return False
            # If Retry-After exceeds max backoff, don't retry: surface the error.
            retry_after = _retry_after_seconds(response)
            if retry_after is not None and retry_after > _MAX_BACKOFF:
                return False
            if is_get:
                return True
            return response.status_code in (429, 503) and "Retry-After" in response.headers
        if is_get:
            return True
        return isinstance(exc, httpx.ConnectError)

    def _finish(
        self,
        response: httpx.Response,
        method: str,
        url: str,
    ) -> Any:
        body = _decode(response)
        if response.is_success:
            return body
        raise status_error_from_response(
            response.status_code,
            body,
            response.headers,
            method=method,
            url=url,
        )


class SyncTransport(_BaseTransport):
    """Blocking transport backed by :class:`httpx.Client`."""

    def __init__(self, config: ClientConfig, http_client: httpx.Client | None = None) -> None:
        super().__init__(config)
        self._owns_client = http_client is None
        # Redirects are off: X-API-Key is a custom header that httpx would forward to
        # another origin on a cross-origin redirect.
        self._http = http_client or httpx.Client(timeout=config.timeout, follow_redirects=False)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        versioned: bool = True,
        timeout: float | None = None,
    ) -> Any:
        url = self._config.url_for(path, versioned)
        headers = self._config.headers()
        query = _clean_params(params)
        extra: dict[str, Any] = {} if timeout is None else {"timeout": timeout}

        for attempt in range(self._config.max_retries + 1):
            try:
                response = self._http.request(
                    method, url, params=query, json=json, headers=headers, **extra
                )
            except httpx.TimeoutException as exc:
                if not self._should_retry(method, attempt, exc=exc):
                    raise APITimeoutError(
                        f"{method} {url} timed out after {attempt + 1} attempt(s)."
                    ) from exc
                time.sleep(_retry_delay(attempt, None))
                continue
            except httpx.TransportError as exc:
                if not self._should_retry(method, attempt, exc=exc):
                    raise APIConnectionError(f"{method} {url} failed: {exc}") from exc
                time.sleep(_retry_delay(attempt, None))
                continue

            if self._should_retry(method, attempt, response):
                time.sleep(_retry_delay(attempt, response))
                continue
            return self._finish(response, method, url)

        raise APIConnectionError(f"{method} {url} exhausted all retries.")  # pragma: no cover

    def close(self) -> None:
        if self._owns_client:
            self._http.close()


class AsyncTransport(_BaseTransport):
    """Non-blocking transport backed by :class:`httpx.AsyncClient`."""

    def __init__(self, config: ClientConfig, http_client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self._owns_client = http_client is None
        # Redirects are off: X-API-Key is a custom header that httpx would forward to
        # another origin on a cross-origin redirect.
        self._http = http_client or httpx.AsyncClient(
            timeout=config.timeout, follow_redirects=False
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        versioned: bool = True,
        timeout: float | None = None,
    ) -> Any:
        url = self._config.url_for(path, versioned)
        headers = self._config.headers()
        query = _clean_params(params)
        extra: dict[str, Any] = {} if timeout is None else {"timeout": timeout}

        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._http.request(
                    method, url, params=query, json=json, headers=headers, **extra
                )
            except httpx.TimeoutException as exc:
                if not self._should_retry(method, attempt, exc=exc):
                    raise APITimeoutError(
                        f"{method} {url} timed out after {attempt + 1} attempt(s)."
                    ) from exc
                await asyncio.sleep(_retry_delay(attempt, None))
                continue
            except httpx.TransportError as exc:
                if not self._should_retry(method, attempt, exc=exc):
                    raise APIConnectionError(f"{method} {url} failed: {exc}") from exc
                await asyncio.sleep(_retry_delay(attempt, None))
                continue

            if self._should_retry(method, attempt, response):
                await asyncio.sleep(_retry_delay(attempt, response))
                continue
            return self._finish(response, method, url)

        raise APIConnectionError(f"{method} {url} exhausted all retries.")  # pragma: no cover

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()


class SyncResource:
    """Base class for blocking resource namespaces."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def _get(self, path: str, **kwargs: Any) -> Any:
        return self._transport.request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs: Any) -> Any:
        return self._transport.request("POST", path, **kwargs)


class AsyncResource:
    """Base class for awaitable resource namespaces."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def _get(self, path: str, **kwargs: Any) -> Any:
        return await self._transport.request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs: Any) -> Any:
        return await self._transport.request("POST", path, **kwargs)


def _seg(value: str, name: str) -> str:
    """Validate and percent-encode a value being interpolated into a URL path.

    Empty segments would silently collapse the path onto a different endpoint,
    and officer ids are opaque upstream tokens, so both are checked and quoted
    rather than trusted.
    """
    if value is None or not str(value).strip():
        raise ValueError(f"{name} must be a non-empty string")
    return quote(str(value).strip(), safe="")


def _charge_key(value: str) -> str:
    """Reject a blank charge key and return it trimmed."""
    if value is None or not str(value).strip():
        raise ValueError("charge_key must be a non-empty string")
    return str(value).strip()


def _names_body(names: Sequence[str], *, limit: int | None = None) -> dict[str, Any]:
    """Build the ``{"names": [...]}`` body used by the batch screening endpoints."""
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    if not cleaned:
        raise ValueError("names must contain at least one non-empty string")
    if limit is not None and len(cleaned) > limit:
        raise ValueError(f"names accepts at most {limit} entries, got {len(cleaned)}")
    return {"names": cleaned}
