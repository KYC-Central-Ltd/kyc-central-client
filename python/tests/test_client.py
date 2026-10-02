"""Client construction, headers, URL building and retry behaviour."""

from __future__ import annotations

import httpx
import pytest
import respx

from kyccentral import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncKYCCentral,
    KYCCentral,
    NotFoundError,
)
from kyccentral._transport import API_KEY_ENV, BASE_URL_ENV, DEFAULT_BASE_URL

from .conftest import BASE_URL


def test_defaults_to_production_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    client = KYCCentral()
    assert client.base_url == DEFAULT_BASE_URL
    assert client.is_authenticated is False


def test_reads_credentials_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "env-key")
    monkeypatch.setenv(BASE_URL_ENV, "https://dev-api.test.invalid/")
    client = KYCCentral()
    assert client.is_authenticated is True
    # Trailing slash is normalised away so path joins never double up.
    assert client.base_url == "https://dev-api.test.invalid"


def test_explicit_arguments_beat_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "env-key")
    client = KYCCentral(api_key="explicit", base_url=BASE_URL)
    assert client.base_url == BASE_URL


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"timeout": -1}, {"max_retries": -1}])
def test_rejects_invalid_settings(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        KYCCentral(api_key="k", **kwargs)


@respx.mock
def test_sends_api_key_and_user_agent(client: KYCCentral) -> None:
    route = respx.get(f"{BASE_URL}/v1/rule-sets").mock(return_value=httpx.Response(200, json=[]))
    client.rule_sets.list()

    request = route.calls[0].request
    assert request.headers["X-API-Key"] == "test-key"
    assert request.headers["User-Agent"].startswith("kyccentral-python/")
    assert request.headers["Accept"] == "application/json"


@respx.mock
def test_omits_api_key_header_when_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    route = respx.get(f"{BASE_URL}/v1/jurisdictions").mock(
        return_value=httpx.Response(200, json={})
    )
    with KYCCentral(base_url=BASE_URL) as client:
        client.jurisdictions.list()

    assert "X-API-Key" not in route.calls[0].request.headers


@respx.mock
def test_health_is_not_versioned(client: KYCCentral) -> None:
    respx.get(f"{BASE_URL}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    assert client.health() == {"status": "ok"}


@respx.mock
def test_custom_default_headers_are_sent() -> None:
    route = respx.get(f"{BASE_URL}/v1/rule-sets").mock(return_value=httpx.Response(200, json=[]))
    with KYCCentral(api_key="k", base_url=BASE_URL, default_headers={"X-Trace": "abc"}) as client:
        client.rule_sets.list()
    assert route.calls[0].request.headers["X-Trace"] == "abc"


@respx.mock
def test_unset_query_parameters_are_dropped(client: KYCCentral) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/companies/search").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    client.companies.search("tesco")

    url = route.calls[0].request.url
    assert url.params["q"] == "tesco"
    # Neither optional parameter was supplied, so neither should appear.
    assert "items_per_page" not in url.params
    assert "start_index" not in url.params


@respx.mock
def test_repeatable_parameters_are_sent_once_per_value(
    client: KYCCentral, assessment_payload
) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    client.kyc.assess("00445790", confirmed_media_urls=["https://a.example", "https://b.example"])

    values = route.calls[0].request.url.params.get_list("confirmed_media_url")
    assert values == ["https://a.example", "https://b.example"]


@respx.mock
def test_path_segments_are_percent_encoded(client: KYCCentral) -> None:
    # Officer ids are opaque upstream tokens and can contain URL-significant bytes.
    route = respx.get(url__startswith=f"{BASE_URL}/v1/companies/officers/").mock(
        return_value=httpx.Response(200, json={})
    )
    client.companies.officer_appointments("abc/def+gh")
    assert "abc%2Fdef%2Bgh" in str(route.calls[0].request.url)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_path_segments_are_rejected(client: KYCCentral, blank: str) -> None:
    with pytest.raises(ValueError, match="company_number"):
        client.companies.get(blank)


@respx.mock
def test_retries_retryable_statuses_then_succeeds() -> None:
    route = respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        side_effect=[
            httpx.Response(503, json={"detail": "warming up"}),
            httpx.Response(200, json=[{"id": "default"}]),
        ]
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=2) as client:
        assert client.rule_sets.list() == [{"id": "default"}]
    assert route.call_count == 2


@respx.mock
def test_does_not_retry_client_errors() -> None:
    route = respx.get(f"{BASE_URL}/v1/companies/99999999").mock(
        return_value=httpx.Response(404, json={"detail": "Company not found"})
    )
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=3) as client:
        with pytest.raises(NotFoundError):
            client.companies.get("99999999")
    assert route.call_count == 1


@respx.mock
def test_connection_errors_surface_after_retries() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(side_effect=httpx.ConnectError("refused"))
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=1) as client:
        with pytest.raises(APIConnectionError):
            client.rule_sets.list()


@respx.mock
def test_timeouts_raise_api_timeout_error() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(side_effect=httpx.ReadTimeout("slow"))
    with KYCCentral(api_key="k", base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(APITimeoutError):
            client.rule_sets.list()


@respx.mock
def test_supplied_http_client_is_not_closed() -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(return_value=httpx.Response(200, json=[]))
    http_client = httpx.Client()
    with KYCCentral(api_key="k", base_url=BASE_URL, http_client=http_client) as client:
        client.rule_sets.list()
    assert not http_client.is_closed
    http_client.close()


@pytest.mark.asyncio
@respx.mock
async def test_async_client_mirrors_sync(async_client: AsyncKYCCentral) -> None:
    respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        return_value=httpx.Response(200, json=[{"id": "default"}])
    )
    assert await async_client.rule_sets.list() == [{"id": "default"}]


@pytest.mark.asyncio
@respx.mock
async def test_async_client_retries() -> None:
    route = respx.get(f"{BASE_URL}/v1/sanctions/status").mock(
        side_effect=[
            httpx.Response(502, text="bad gateway"),
            httpx.Response(200, json={"available": True}),
        ]
    )
    async with AsyncKYCCentral(api_key="k", base_url=BASE_URL, max_retries=1) as client:
        assert await client.sanctions.status() == {"available": True}
    assert route.call_count == 2


def _post_client(**kwargs) -> KYCCentral:
    return KYCCentral(api_key="k", base_url=BASE_URL, max_retries=2, **kwargs)


@respx.mock
def test_post_is_not_retried_after_a_timeout() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json={})]
    )
    with _post_client() as client:
        with pytest.raises(APITimeoutError):
            client.docs.ask("hi")
    assert route.call_count == 1


@respx.mock
def test_post_is_retried_after_connection_refused() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json={"ok": 1})]
    )
    with _post_client() as client:
        assert client.docs.ask("hi") == {"ok": 1}
    assert route.call_count == 2


@respx.mock
def test_post_is_not_retried_after_a_connect_timeout() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(200, json={})]
    )
    with _post_client() as client:
        with pytest.raises(APITimeoutError):
            client.docs.ask("hi")
    assert route.call_count == 1


@respx.mock
def test_post_is_not_retried_on_502() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.Response(502, text="bad gateway"), httpx.Response(200, json={})]
    )
    with _post_client() as client:
        with pytest.raises(APIStatusError) as info:
            client.docs.ask("hi")
    assert info.value.status_code == 502
    assert route.call_count == 1


@respx.mock
def test_post_is_retried_on_503_with_retry_after() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "0"}, json={"detail": "later"}),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    with _post_client() as client:
        assert client.docs.ask("hi") == {"ok": 1}
    assert route.call_count == 2


@respx.mock
def test_post_is_not_retried_on_503_without_retry_after() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.Response(503, json={"detail": "x"}), httpx.Response(200, json={})]
    )
    with _post_client() as client:
        with pytest.raises(APIStatusError):
            client.docs.ask("hi")
    assert route.call_count == 1


@respx.mock
def test_post_is_not_retried_after_an_unsafe_transport_error() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.ReadError("reset"), httpx.Response(200, json={})]
    )
    with _post_client() as client:
        with pytest.raises(APIConnectionError):
            client.docs.ask("hi")
    assert route.call_count == 1


@respx.mock
def test_get_is_retried_after_a_timeout() -> None:
    route = respx.get(f"{BASE_URL}/v1/rule-sets").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json=[])]
    )
    with _post_client() as client:
        assert client.rule_sets.list() == []
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_async_post_is_not_retried_after_a_timeout() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json={})]
    )
    async with AsyncKYCCentral(api_key="k", base_url=BASE_URL, max_retries=2) as client:
        with pytest.raises(APITimeoutError):
            await client.docs.ask("hi")
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_async_post_is_retried_after_connection_refused() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json={"ok": 1})]
    )
    async with AsyncKYCCentral(api_key="k", base_url=BASE_URL, max_retries=2) as client:
        assert await client.docs.ask("hi") == {"ok": 1}
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_async_post_retry_after_and_502_policy() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={}),
            httpx.Response(502, text="bad gateway"),
            httpx.Response(200, json={}),
        ]
    )
    async with AsyncKYCCentral(api_key="k", base_url=BASE_URL, max_retries=2) as client:
        with pytest.raises(APIStatusError):
            await client.docs.ask("hi")
    assert route.call_count == 2
