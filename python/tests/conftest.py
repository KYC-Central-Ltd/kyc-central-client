"""Shared fixtures. Every test runs against a mocked transport — no network."""

from __future__ import annotations

from typing import Any

import pytest

from kyccentral import AsyncKYCCentral, KYCCentral

BASE_URL = "https://api.test.invalid"


@pytest.fixture
def client() -> KYCCentral:
    with KYCCentral(api_key="test-key", base_url=BASE_URL, max_retries=0) as c:
        yield c


@pytest.fixture
async def async_client() -> AsyncKYCCentral:
    async with AsyncKYCCentral(api_key="test-key", base_url=BASE_URL, max_retries=0) as c:
        yield c


@pytest.fixture
def assessment_payload() -> dict[str, Any]:
    """A minimal but realistic ``/v1/kyc/assess`` body."""
    return {
        "company_number": "00445790",
        "company_name": "TESCO PLC",
        "risk_level": "medium",
        "checked_at": "2026-08-13T10:00:00+00:00",
        "data_fetched_at": "2026-08-13T09:55:00+00:00",
        "flags": [
            {
                "code": "ACCOUNTS_OVERDUE",
                "severity": "high",
                "description": "Annual accounts are 42 days overdue.",
            },
            {
                "code": "ADVERSE_MEDIA_UNCONFIRMED",
                "severity": "low",
                "description": "3 possible adverse media matches require review.",
            },
        ],
        "profile": {"company_status": "active"},
        "officers_summary": {"total": 12},
        "psc_summary": {"total": 3},
        "psc_chain_depth": 2,
        "psc_chain_depth_capped": False,
        "charges_summary": {},
        "insolvency_summary": {},
        "filing_summary": {},
        "disqualifications_summary": {},
        "rule_results": [
            {
                "code": "ACCOUNTS_OVERDUE",
                "name": "Accounts overdue",
                "description": "Checks whether annual accounts are past their due date.",
                "severity": "high",
                "status": "failed",
                "reason": "Annual accounts are 42 days overdue.",
            },
            {
                "code": "COMPANY_NOT_ACTIVE",
                "name": "Company not active",
                "description": "Checks the company is trading.",
                "severity": "critical",
                "status": "passed",
                "reason": None,
            },
        ],
        "timed_out_services": [],
        "unavailable_services": [],
        "failed_rules": [],
        "pending_extractions": [],
    }
