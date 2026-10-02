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
    result = client.kyc.assess("00445790", poll_interval=0)

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
        client.kyc.assess("00445790", poll_interval=0)
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
        client.kyc.assess("00445790", poll_interval=0)


@respx.mock
def test_poll_timeout_raises(client: KYCCentral) -> None:
    respx.get(url__startswith=f"{BASE_URL}/v1/kyc/assess").mock(
        return_value=httpx.Response(202, json=_queued())
    )
    respx.get(f"{BASE_URL}/v1/jobs/job-123").mock(
        return_value=httpx.Response(200, json={"job_id": "job-123", "status": "running"})
    )
    with pytest.raises(JobTimeoutError, match="job-123"):
        client.kyc.assess("00445790", poll_interval=0.01, poll_timeout=0.0)


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
    result = await async_client.kyc.assess("00445790", poll_interval=0)
    assert isinstance(result, Assessment)
    assert result.risk_level is RiskLevel.MEDIUM
