"""Assessment parsing, argument validation and queued-job polling."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from kyccentral import (
    Assessment,
    AsyncKYCCentral,
    JobFailedError,
    JobTimeoutError,
    KYCCentral,
    RiskLevel,
    RuleStatus,
)

from .conftest import BASE_URL


@respx.mock
def test_assess_returns_a_typed_assessment(client: KYCCentral, assessment_payload) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    result = client.kyc.assess("00445790")

    assert isinstance(result, Assessment)
    assert result.company_name == "TESCO PLC"
    assert result.risk_level is RiskLevel.MEDIUM
    assert result.psc_chain_depth == 2
    assert len(result) == 2
    assert [f.code for f in result] == ["ACCOUNTS_OVERDUE", "ADVERSE_MEDIA_UNCONFIRMED"]


@respx.mock
def test_assessment_helpers(client: KYCCentral, assessment_payload) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    result = client.kyc.assess("00445790")

    assert result.is_clear is False
    assert result.is_partial is False
    assert result.critical_flags == []
    assert [f.code for f in result.high_flags] == ["ACCOUNTS_OVERDUE"]
    assert [f.code for f in result.flags_at_or_above(RiskLevel.MEDIUM)] == ["ACCOUNTS_OVERDUE"]
    assert result.has_flag("ACCOUNTS_OVERDUE") is True
    assert result.has_flag("NOT_RAISED") is False
    assert result.flag("NOT_RAISED") is None
    assert [r.code for r in result.rules_with_status(RuleStatus.PASSED)] == ["COMPANY_NOT_ACTIVE"]
    # Anything not mapped to an attribute is still reachable.
    assert result.raw["profile"]["company_status"] == "active"


@respx.mock
def test_partial_assessments_are_flagged(client: KYCCentral, assessment_payload) -> None:
    assessment_payload["timed_out_services"] = ["sanctions"]
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    assert client.kyc.assess("00445790").is_partial is True


@respx.mock
def test_assessment_partial_when_only_unavailable_services(
    client: KYCCentral, assessment_payload
) -> None:
    assessment_payload["unavailable_services"] = ["fca"]
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    result = client.kyc.assess("00445790")
    assert result.unavailable_services == ["fca"]
    assert result.timed_out_services == []
    assert result.is_partial is True


def test_new_assessment_fields_parse_and_default(assessment_payload) -> None:
    parsed = Assessment.from_dict(assessment_payload)
    assert parsed.psc_chain_depth_capped is False
    assert parsed.unavailable_services == []

    assessment_payload["psc_chain_depth_capped"] = True
    assessment_payload["unavailable_services"] = ["gleif", "fca"]
    parsed = Assessment.from_dict(assessment_payload)
    assert parsed.psc_chain_depth_capped is True
    assert parsed.unavailable_services == ["gleif", "fca"]

    del assessment_payload["psc_chain_depth_capped"]
    del assessment_payload["unavailable_services"]
    parsed = Assessment.from_dict(assessment_payload)
    assert parsed.psc_chain_depth_capped is False
    assert parsed.unavailable_services == []


@respx.mock
def test_unknown_severity_does_not_crash_parsing(client: KYCCentral, assessment_payload) -> None:
    # A future API release may add a severity this client version predates.
    assessment_payload["flags"][0]["severity"] = "catastrophic"
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    result = client.kyc.assess("00445790")
    assert result.flags[0].severity is RiskLevel.UNKNOWN
    assert result.flags[0].raw["severity"] == "catastrophic"


def test_unrecognised_levels_fail_safe_to_unknown(assessment_payload) -> None:
    assessment_payload["risk_level"] = "severe"
    assessment_payload["flags"][1]["severity"] = "severe"
    result = Assessment.from_dict(assessment_payload)
    assert result.risk_level is RiskLevel.UNKNOWN
    unknown_flag = result.flags[1]
    assert unknown_flag.severity is RiskLevel.UNKNOWN
    assert unknown_flag.raw["severity"] == "severe"
    assert unknown_flag in result.flags_at_or_above(RiskLevel.HIGH)
    assert unknown_flag in result.flags_at_or_above(RiskLevel.CRITICAL)
    assert RiskLevel.UNKNOWN.rank > RiskLevel.CRITICAL.rank


def test_missing_or_non_string_severity_is_unknown(assessment_payload) -> None:
    del assessment_payload["risk_level"]
    assessment_payload["flags"][0]["severity"] = None
    assessment_payload["flags"][1]["severity"] = 3
    result = Assessment.from_dict(assessment_payload)
    assert result.risk_level is RiskLevel.UNKNOWN
    assert [f.severity for f in result.flags] == [RiskLevel.UNKNOWN, RiskLevel.UNKNOWN]


def test_known_severity_is_case_insensitive(assessment_payload) -> None:
    assessment_payload["flags"][0]["severity"] = "HIGH"
    assert Assessment.from_dict(assessment_payload).flags[0].severity is RiskLevel.HIGH


def test_assess_requires_exactly_one_selector(client: KYCCentral) -> None:
    with pytest.raises(ValueError, match="either"):
        client.kyc.assess()
    with pytest.raises(ValueError, match="not both"):
        client.kyc.assess("00445790", q="tesco")


@respx.mock
def test_assess_by_name_sends_q(client: KYCCentral, assessment_payload) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    client.kyc.assess(q="tesco plc", rule_set_id="quick")

    params = route.calls[0].request.url.params
    assert params["q"] == "tesco plc"
    assert params["rule_set_id"] == "quick"
    assert "company_number" not in params


_NEW_ASSESS_KWARGS: dict[str, Any] = {
    "dismissed_media_urls": ["https://a.example", "https://b.example"],
    "dismissed_leak_ids": ["n1", "n2"],
    "confirmed_officer_company_links": ["ACME LTD||00000001", "FOO LTD||00000002"],
    "confirmed_fca_frn": "123456",
    "fca_not_applicable": True,
}


def _check_new_assess_params(params: Any) -> None:
    assert params.get_list("dismissed_media_url") == ["https://a.example", "https://b.example"]
    assert params.get_list("dismissed_leak_id") == ["n1", "n2"]
    assert params.get_list("confirmed_officer_company_link") == [
        "ACME LTD||00000001",
        "FOO LTD||00000002",
    ]
    assert params.get_list("confirmed_fca_frn") == ["123456"]
    assert params.get_list("fca_not_applicable") == ["true"]


@respx.mock
def test_assess_sends_new_options(client: KYCCentral, assessment_payload) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    client.kyc.assess("00445790", **_NEW_ASSESS_KWARGS)
    _check_new_assess_params(route.calls[0].request.url.params)


@pytest.mark.parametrize("kwargs", [{}, {"fca_not_applicable": False}])
@respx.mock
def test_assess_omits_new_options_when_unset(
    client: KYCCentral, assessment_payload, kwargs: dict[str, Any]
) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    client.kyc.assess("00445790", **kwargs)
    params = route.calls[0].request.url.params
    for key in (
        "dismissed_media_url",
        "dismissed_leak_id",
        "confirmed_officer_company_link",
        "confirmed_fca_frn",
        "fca_not_applicable",
    ):
        assert key not in params


@pytest.mark.asyncio
@respx.mock
async def test_async_assess_sends_new_options(
    async_client: AsyncKYCCentral, assessment_payload
) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(200, json=assessment_payload)
    )
    await async_client.kyc.assess("00445790", **_NEW_ASSESS_KWARGS)
    _check_new_assess_params(route.calls[0].request.url.params)
    await async_client.kyc.assess("00445790")
    assert "fca_not_applicable" not in route.calls[1].request.url.params


# ── Queued assessments ───────────────────────────────────────────────────────


def _queued() -> dict[str, Any]:
    return {"job_id": "job-123", "status": "queued"}


@respx.mock
def test_queued_assessment_is_polled_to_completion(client: KYCCentral, assessment_payload) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    job_route = respx.get(f"{BASE_URL}/v1/jobs/job-123").mock(
        side_effect=[
            httpx.Response(200, json={"job_id": "job-123", "status": "queued"}),
            httpx.Response(200, json={"job_id": "job-123", "status": "running"}),
            httpx.Response(
                200, json={"job_id": "job-123", "status": "done", "result": assessment_payload}
            ),
        ]
    )
    result = client.kyc.assess("00445790", poll_interval=0.001)

    assert isinstance(result, Assessment)
    assert result.company_name == "TESCO PLC"
    assert job_route.call_count == 3


@respx.mock
def test_wait_false_returns_the_job_envelope(client: KYCCentral) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    result = client.kyc.assess("00445790", wait=False)
    assert result == {"job_id": "job-123", "status": "queued"}


@respx.mock
def test_failed_job_raises(client: KYCCentral) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    respx.get(f"{BASE_URL}/v1/jobs/job-123").mock(
        return_value=httpx.Response(
            200, json={"job_id": "job-123", "status": "error", "error": "upstream exploded"}
        )
    )
    with pytest.raises(JobFailedError, match="upstream exploded") as excinfo:
        client.kyc.assess("00445790", poll_interval=0.001)
    assert excinfo.value.job_id == "job-123"


@respx.mock
def test_expired_job_result_raises(client: KYCCentral) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    respx.get(f"{BASE_URL}/v1/jobs/job-123").mock(
        return_value=httpx.Response(200, json={"job_id": "job-123", "status": "done"})
    )
    with pytest.raises(JobFailedError, match="no longer available"):
        client.kyc.assess("00445790", poll_interval=0.001)


@respx.mock
def test_poll_timeout_raises(client: KYCCentral) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    respx.get(f"{BASE_URL}/v1/jobs/job-123").mock(
        return_value=httpx.Response(200, json={"job_id": "job-123", "status": "running"})
    )
    with pytest.raises(JobTimeoutError, match="job-123"):
        client.kyc.assess("00445790", poll_interval=0.01, poll_timeout=0.001)


@pytest.mark.asyncio
@respx.mock
async def test_async_queued_assessment_is_polled(
    async_client: AsyncKYCCentral, assessment_payload
) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    respx.get(f"{BASE_URL}/v1/jobs/job-123").mock(
        side_effect=[
            httpx.Response(200, json={"job_id": "job-123", "status": "running"}),
            httpx.Response(
                200, json={"job_id": "job-123", "status": "done", "result": assessment_payload}
            ),
        ]
    )
    result = await async_client.kyc.assess("00445790", poll_interval=0.001)
    assert isinstance(result, Assessment)
    assert result.risk_level is RiskLevel.MEDIUM


def test_clean_assessment_is_truthy(assessment_payload) -> None:
    assessment_payload["flags"] = []
    result = Assessment.from_dict(assessment_payload)
    assert len(result) == 0
    assert result.is_clear
    assert bool(result) is True
    assert result


_BAD_POLL_ARGS = [
    ({"poll_interval": 0}, "poll_interval must be > 0"),
    ({"poll_interval": -1}, "poll_interval must be > 0"),
    ({"poll_timeout": 0}, "poll_timeout must be > 0"),
    ({"poll_timeout": -5.0}, "poll_timeout must be > 0"),
]


@respx.mock
@pytest.mark.parametrize(("kwargs", "message"), _BAD_POLL_ARGS)
def test_assess_rejects_non_positive_poll_args(
    client: KYCCentral, kwargs: dict[str, Any], message: str
) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess")
    with pytest.raises(ValueError, match=message):
        client.kyc.assess("00445790", **kwargs)
    assert route.call_count == 0
    assert respx.calls.call_count == 0


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(("kwargs", "message"), _BAD_POLL_ARGS)
async def test_async_assess_rejects_non_positive_poll_args(
    async_client: AsyncKYCCentral, kwargs: dict[str, Any], message: str
) -> None:
    route = respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess")
    with pytest.raises(ValueError, match=message):
        await async_client.kyc.assess("00445790", **kwargs)
    assert route.call_count == 0
    assert respx.calls.call_count == 0
