"""Every resource method targets the URL and body the API documents."""

from __future__ import annotations

import httpx
import pytest
import respx

from kyccentral import AsyncKYCCentral, KYCCentral

from .conftest import BASE_URL


@pytest.mark.parametrize(
    ("call", "method", "path"),
    [
        (lambda c: c.companies.get("00445790"), "GET", "/v1/companies/00445790"),
        (lambda c: c.companies.dossier("00445790"), "GET", "/v1/companies/00445790/dossier"),
        (lambda c: c.companies.officers("00445790"), "GET", "/v1/companies/00445790/officers"),
        (
            lambda c: c.companies.pscs("00445790"),
            "GET",
            "/v1/companies/00445790/persons-with-significant-control",
        ),
        (
            lambda c: c.companies.psc_statements("00445790"),
            "GET",
            "/v1/companies/00445790/persons-with-significant-control-statements",
        ),
        (
            lambda c: c.companies.psc_chain_depth("00445790"),
            "GET",
            "/v1/companies/00445790/psc-chain-depth",
        ),
        (
            lambda c: c.companies.psc_chain_tree("00445790"),
            "GET",
            "/v1/companies/00445790/psc-chain-tree",
        ),
        (lambda c: c.companies.charges("00445790"), "GET", "/v1/companies/00445790/charges"),
        (
            lambda c: c.companies.charge("00445790", "chg1"),
            "GET",
            "/v1/companies/00445790/charges/chg1",
        ),
        (
            lambda c: c.companies.insolvency("00445790"),
            "GET",
            "/v1/companies/00445790/insolvency",
        ),
        (
            lambda c: c.companies.disqualifications("00445790"),
            "GET",
            "/v1/companies/00445790/disqualifications",
        ),
        (
            lambda c: c.companies.officer_disqualification("00445790", "off1"),
            "GET",
            "/v1/companies/00445790/officers/off1/disqualification",
        ),
        (
            lambda c: c.companies.filing_history("00445790"),
            "GET",
            "/v1/companies/00445790/filing-history",
        ),
        (
            lambda c: c.companies.filing_extract("00445790", "tx1"),
            "GET",
            "/v1/companies/00445790/filing-history/tx1/extract",
        ),
        (
            lambda c: c.companies.statement_of_capital("00445790"),
            "GET",
            "/v1/companies/00445790/statement-of-capital",
        ),
        (lambda c: c.rule_sets.list(), "GET", "/v1/rule-sets"),
        (lambda c: c.rules.list(), "GET", "/v1/rules"),
        (lambda c: c.rules.fields(), "GET", "/v1/rules/fields"),
        (lambda c: c.jurisdictions.list(), "GET", "/v1/jurisdictions"),
        (lambda c: c.offshore_jurisdictions.list(), "GET", "/v1/offshore-jurisdictions"),
        (lambda c: c.sanctions.status(), "GET", "/v1/sanctions/status"),
        (lambda c: c.sanctions.meta(), "GET", "/v1/sanctions/meta"),
        (lambda c: c.sanctions.entities(), "GET", "/v1/sanctions/entities"),
        (lambda c: c.news.status(), "GET", "/v1/news/status"),
        (lambda c: c.offshore_leaks.status(), "GET", "/v1/offshore-leaks/status"),
        (lambda c: c.offshore_leaks.node("n1"), "GET", "/v1/offshore-leaks/node/n1"),
        (lambda c: c.fca.status(), "GET", "/v1/fca/status"),
        (lambda c: c.fca.firm("123456"), "GET", "/v1/fca/firm/123456"),
        (lambda c: c.fca.firm_names("123456"), "GET", "/v1/fca/firm/123456/names"),
        (lambda c: c.fca.firm_individuals("123456"), "GET", "/v1/fca/firm/123456/individuals"),
        (lambda c: c.gleif.company("00445790"), "GET", "/v1/gleif/company"),
        (
            lambda c: c.individual_insolvency.screen_company("00445790"),
            "GET",
            "/v1/individual-insolvency/screen-company",
        ),
        (lambda c: c.charity.status(), "GET", "/v1/charity/status"),
        (lambda c: c.charity.get("1234"), "GET", "/v1/charity/charity/1234"),
        (lambda c: c.charity.trustees("1234"), "GET", "/v1/charity/charity/1234/trustees"),
        (lambda c: c.hmrc_vat.status(), "GET", "/v1/hmrc-vat/status"),
        (lambda c: c.analysis.status(), "GET", "/v1/analysis/status"),
        (lambda c: c.jobs.get("job-1"), "GET", "/v1/jobs/job-1"),
    ],
)
@respx.mock
def test_endpoint_routing(client: KYCCentral, call, method: str, path: str) -> None:
    route = respx.request(method, url__startswith=f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json={})
    )
    call(client)
    assert route.called
    assert route.calls[0].request.url.path == path


@respx.mock
def test_sanctions_screen_names_posts_a_names_body(client: KYCCentral) -> None:
    import json

    route = respx.post(f"{BASE_URL}/v1/sanctions/screen-names").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client.sanctions.screen_names(["Alice Example", "  Bob Example  ", ""])

    body = json.loads(route.calls[0].request.content)
    # Blank entries dropped, surrounding whitespace trimmed.
    assert body == {"names": ["Alice Example", "Bob Example"]}


def test_screen_names_rejects_empty_input(client: KYCCentral) -> None:
    with pytest.raises(ValueError, match="at least one"):
        client.sanctions.screen_names([])
    with pytest.raises(ValueError, match="at least one"):
        client.offshore_leaks.screen_names(["", "   "])


def test_screen_names_enforces_the_documented_batch_cap(client: KYCCentral) -> None:
    with pytest.raises(ValueError, match="at most 500"):
        client.sanctions.screen_names([f"name {i}" for i in range(501)])


@respx.mock
def test_news_search_entities_validates_shape(client: KYCCentral) -> None:
    import json

    route = respx.post(f"{BASE_URL}/v1/news/search-entities").mock(
        return_value=httpx.Response(200, json={})
    )
    client.news.search_entities([{"key": "psc-1", "names": ["Alice Example", "A. Example"]}])

    body = json.loads(route.calls[0].request.content)
    assert body == {"entities": [{"key": "psc-1", "names": ["Alice Example", "A. Example"]}]}

    with pytest.raises(ValueError, match="non-empty 'key'"):
        client.news.search_entities([{"names": ["Alice"]}])
    with pytest.raises(ValueError, match="at least one name"):
        client.news.search_entities([{"key": "psc-1", "names": []}])


@respx.mock
def test_analysis_company_body(client: KYCCentral) -> None:
    import json

    route = respx.post(f"{BASE_URL}/v1/analysis/company").mock(
        return_value=httpx.Response(200, json={})
    )
    client.analysis.company("00445790", rule_set_id="quick", sections=["ownership"])

    body = json.loads(route.calls[0].request.content)
    assert body == {
        "company_number": "00445790",
        "rule_set_id": "quick",
        "sections": ["ownership"],
    }


def test_analysis_filing_extract_validates_mode(client: KYCCentral) -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        client.analysis.filing_extract("00445790", "tx1", mode="summarise")


def test_docs_ask_validates_input(client: KYCCentral) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        client.docs.ask("   ")
    with pytest.raises(ValueError, match="at most 12"):
        client.docs.ask("hi", history=[{"role": "user", "content": "x"}] * 13)


@respx.mock
def test_advanced_search_repeats_list_filters(client: KYCCentral) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/companies/advanced-search").mock(
        return_value=httpx.Response(200, json={})
    )
    client.companies.advanced_search(
        company_name_includes="tesco", company_status=["active", "liquidation"]
    )

    params = route.calls[0].request.url.params
    assert params.get_list("company_status") == ["active", "liquidation"]
    assert params["company_name_includes"] == "tesco"


def _read_timeout(route: respx.Route) -> float:
    return route.calls[-1].request.extensions["timeout"]["read"]


def _ai_calls(c):
    return [
        ("/v1/analysis/company", lambda **kw: c.analysis.company("00445790", **kw)),
        (
            "/v1/analysis/adverse-media-overview",
            lambda **kw: c.analysis.adverse_media_overview("1", **kw),
        ),
        ("/v1/analysis/filing-extract", lambda **kw: c.analysis.filing_extract("1", "tx", **kw)),
        ("/v1/docs/ask", lambda **kw: c.docs.ask("hi", **kw)),
    ]


@pytest.mark.parametrize("index", range(4))
@respx.mock
def test_ai_endpoints_default_to_120s_and_accept_overrides(index: int) -> None:
    with KYCCentral(api_key="k", base_url=BASE_URL) as default_client:
        path, call = _ai_calls(default_client)[index]
        route = respx.post(f"{BASE_URL}{path}").mock(return_value=httpx.Response(200, json={}))
        call()
        assert _read_timeout(route) == 120.0
        call(timeout=5.0)
        assert _read_timeout(route) == 5.0
        for bad in (0, -1):
            with pytest.raises(ValueError, match="timeout"):
                call(timeout=bad)
        assert route.call_count == 2
    with KYCCentral(api_key="k", base_url=BASE_URL, timeout=300.0) as slow_client:
        path, call = _ai_calls(slow_client)[index]
        route = respx.post(f"{BASE_URL}{path}").mock(return_value=httpx.Response(200, json={}))
        call()
        assert _read_timeout(route) == 300.0


@respx.mock
def test_non_ai_posts_keep_the_client_timeout() -> None:
    route = respx.post(f"{BASE_URL}/v1/sanctions/screen-names").mock(
        return_value=httpx.Response(200, json={})
    )
    with KYCCentral(api_key="k", base_url=BASE_URL) as client:
        client.sanctions.screen_names(["A"])
    assert _read_timeout(route) == 30.0


@pytest.mark.asyncio
@respx.mock
async def test_async_ai_endpoints_timeout() -> None:
    route = respx.post(f"{BASE_URL}/v1/docs/ask").mock(return_value=httpx.Response(200, json={}))
    comp = respx.post(f"{BASE_URL}/v1/analysis/company").mock(
        return_value=httpx.Response(200, json={})
    )
    async with AsyncKYCCentral(api_key="k", base_url=BASE_URL) as client:
        await client.docs.ask("hi")
        assert _read_timeout(route) == 120.0
        await client.analysis.company("1", timeout=7.0)
        assert _read_timeout(comp) == 7.0
        with pytest.raises(ValueError, match="timeout"):
            await client.docs.ask("hi", timeout=0)
        with pytest.raises(ValueError, match="timeout"):
            await client.analysis.filing_extract("1", "tx", timeout=-1)
    assert route.call_count == 1
    async with AsyncKYCCentral(api_key="k", base_url=BASE_URL, timeout=300.0) as big:
        await big.docs.ask("hi")
        assert route.calls[-1].request.extensions["timeout"]["read"] == 300.0
