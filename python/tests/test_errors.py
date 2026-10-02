"""Status codes map onto the documented exception types."""

from __future__ import annotations

import httpx
import pytest
import respx

from kyccentral import (
    AuthenticationError,
    BadRequestError,
    KYCCentral,
    KYCCentralError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)

from .conftest import BASE_URL


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (422, UnprocessableEntityError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServiceUnavailableError),
    ],
)
@respx.mock
def test_status_codes_map_to_exception_types(status_code: int, expected: type) -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(status_code, json={"detail": "nope"})
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(expected) as excinfo:
            client.rule_sets.list()

    error = excinfo.value
    assert isinstance(error, KYCCentralError)
    assert error.status_code == status_code
    assert error.detail == "nope"
    assert "nope" in str(error)


@respx.mock
def test_rate_limit_error_exposes_retry_after() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(
            429,
            json={"detail": "Rate limit exceeded: 60 requests per minute."},
            headers={"Retry-After": "30"},
        )
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(RateLimitError) as excinfo:
            client.rule_sets.list()

    assert excinfo.value.retry_after == 30.0
    # Header lookup stays case-insensitive, as HTTP header names are.
    assert excinfo.value.headers["Retry-After"] == "30"
    assert excinfo.value.headers["retry-after"] == "30"


@respx.mock
def test_service_unavailable_error_exposes_retry_after() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(
            503, json={"detail": "try later"}, headers={"Retry-After": "300"}
        )
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(ServiceUnavailableError) as excinfo:
            client.rule_sets.list()
    assert excinfo.value.retry_after == 300.0
    assert excinfo.value.status_code == 503


@respx.mock
def test_service_unavailable_error_without_header_has_no_retry_after() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(503, json={"detail": "try later"})
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(ServiceUnavailableError) as excinfo:
            client.rule_sets.list()
    assert excinfo.value.retry_after is None


@respx.mock
def test_validation_errors_are_flattened_into_the_message() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(
            422,
            json={
                "detail": [
                    {"loc": ["body", "names"], "msg": "field required", "type": "missing"},
                    {"loc": ["query", "q"], "msg": "too long", "type": "value_error"},
                ]
            },
        )
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(UnprocessableEntityError) as excinfo:
            client.rule_sets.list()

    assert "names: field required" in excinfo.value.detail
    assert "query.q: too long" in excinfo.value.detail
    # The structured body stays reachable for callers that want the raw errors.
    assert isinstance(excinfo.value.body["detail"], list)


@respx.mock
def test_non_json_error_bodies_do_not_crash() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(502, text="<html>Bad Gateway</html>")
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(ServerError) as excinfo:
            client.rule_sets.list()

    assert excinfo.value.status_code == 502


@respx.mock
def test_empty_success_body_decodes_to_none() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(return_value=httpx.Response(204))
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        assert client.rule_sets.list() is None
