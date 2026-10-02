"""Typed models for the KYC assessment result.

Most endpoints in this API proxy or reshape upstream registry data (Companies
House, the FCA Register, GLEIF, …) and are returned as plain ``dict`` objects so
that new upstream fields are never silently dropped. The assessment produced by
``client.kyc.assess()`` is the one response with a contract of its own, so it is
modelled here.

Every model keeps the untouched payload on ``.raw``, so anything not mapped to an
attribute is still reachable.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["Assessment", "RiskFlag", "RiskLevel", "RuleResult", "RuleStatus"]


class RiskLevel(str, Enum):
    """Severity of a risk flag, and the overall risk level of an assessment.

    ``UNKNOWN`` is a value this client version does not recognise. It ranks above
    ``CRITICAL`` so it is never filtered out by :meth:`Assessment.flags_at_or_above`;
    the original string is on ``raw``.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

    @property
    def rank(self) -> int:
        """Numeric severity, ascending. Useful for sorting and comparisons."""
        return _RISK_RANK[self]


_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
    RiskLevel.UNKNOWN: 4,
}


class RuleStatus(str, Enum):
    """Outcome of a single rule within an assessment."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


def _coerce_risk_level(value: Any) -> RiskLevel:
    """Map an API severity string onto :class:`RiskLevel`.

    Anything unrecognised (a new API value, or a missing or non-string one) fails
    safe to :attr:`RiskLevel.UNKNOWN`, which ranks above critical, rather than
    being silently treated as low.
    """
    if not isinstance(value, str):
        return RiskLevel.UNKNOWN
    try:
        return RiskLevel(value.lower())
    except ValueError:
        return RiskLevel.UNKNOWN


def _coerce_rule_status(value: Any) -> RuleStatus:
    try:
        return RuleStatus(str(value).lower())
    except ValueError:
        return RuleStatus.NOT_EVALUATED


@dataclass(frozen=True)
class RiskFlag:
    """A single risk signal raised against a company."""

    code: str
    severity: RiskLevel
    description: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RiskFlag:
        return cls(
            code=str(data.get("code", "")),
            severity=_coerce_risk_level(data.get("severity")),
            description=str(data.get("description", "")),
            raw=dict(data),
        )


@dataclass(frozen=True)
class RuleResult:
    """The per-rule breakdown of an assessment, including rules that passed."""

    code: str
    name: str
    description: str
    severity: RiskLevel
    status: RuleStatus
    reason: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuleResult:
        return cls(
            code=str(data.get("code", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            severity=_coerce_risk_level(data.get("severity")),
            status=_coerce_rule_status(data.get("status")),
            reason=data.get("reason"),
            raw=dict(data),
        )


@dataclass
class Assessment:
    """The result of running a rule set against one company.

    The ``*_summary`` attributes hold the evidence each rule was evaluated
    against — the shape of each mirrors the corresponding standalone endpoint, so
    ``assessment.officers_summary`` and ``client.companies.officers(...)``
    describe the same data.
    """

    # Identity and outcome
    company_number: str
    company_name: str
    risk_level: RiskLevel
    flags: list[RiskFlag]
    checked_at: str
    data_fetched_at: str

    # Companies House core data
    profile: dict[str, Any] = field(default_factory=dict, repr=False)
    officers_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    psc_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    psc_chain_depth: int = 0
    psc_statements_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    charges_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    insolvency_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    filing_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    disqualifications_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    corporate_disqualifications_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    officer_appointments_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    company_exemptions_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    confirmation_statements_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    cs01_document_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    statement_of_capital_summary: dict[str, Any] = field(default_factory=dict, repr=False)

    # Screening and external data
    sanctions_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    adverse_media_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    fca_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    individual_insolvency_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    gleif_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    offshore_leaks_summary: dict[str, Any] = field(default_factory=dict, repr=False)
    vat_summary: dict[str, Any] = field(default_factory=dict, repr=False)

    # Run metadata
    timed_out_services: list[str] = field(default_factory=list)
    failed_rules: list[str] = field(default_factory=list)
    rule_results: list[RuleResult] = field(default_factory=list, repr=False)
    pending_extractions: list[str] = field(default_factory=list)

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Assessment:
        """Build an :class:`Assessment` from a decoded ``/v1/kyc/assess`` body."""
        flags = [RiskFlag.from_dict(f) for f in data.get("flags", []) if isinstance(f, Mapping)]
        rule_results = [
            RuleResult.from_dict(r) for r in data.get("rule_results", []) if isinstance(r, Mapping)
        ]

        def _dict(key: str) -> dict[str, Any]:
            value = data.get(key)
            return dict(value) if isinstance(value, Mapping) else {}

        def _list(key: str) -> list[str]:
            value = data.get(key)
            return [str(v) for v in value] if isinstance(value, (list, tuple)) else []

        return cls(
            company_number=str(data.get("company_number", "")),
            company_name=str(data.get("company_name", "")),
            risk_level=_coerce_risk_level(data.get("risk_level")),
            flags=flags,
            checked_at=str(data.get("checked_at", "")),
            data_fetched_at=str(data.get("data_fetched_at", "")),
            profile=_dict("profile"),
            officers_summary=_dict("officers_summary"),
            psc_summary=_dict("psc_summary"),
            psc_chain_depth=int(data.get("psc_chain_depth") or 0),
            psc_statements_summary=_dict("psc_statements_summary"),
            charges_summary=_dict("charges_summary"),
            insolvency_summary=_dict("insolvency_summary"),
            filing_summary=_dict("filing_summary"),
            disqualifications_summary=_dict("disqualifications_summary"),
            corporate_disqualifications_summary=_dict("corporate_disqualifications_summary"),
            officer_appointments_summary=_dict("officer_appointments_summary"),
            company_exemptions_summary=_dict("company_exemptions_summary"),
            confirmation_statements_summary=_dict("confirmation_statements_summary"),
            cs01_document_summary=_dict("cs01_document_summary"),
            statement_of_capital_summary=_dict("statement_of_capital_summary"),
            sanctions_summary=_dict("sanctions_summary"),
            adverse_media_summary=_dict("adverse_media_summary"),
            fca_summary=_dict("fca_summary"),
            individual_insolvency_summary=_dict("individual_insolvency_summary"),
            gleif_summary=_dict("gleif_summary"),
            offshore_leaks_summary=_dict("offshore_leaks_summary"),
            vat_summary=_dict("vat_summary"),
            timed_out_services=_list("timed_out_services"),
            failed_rules=_list("failed_rules"),
            rule_results=rule_results,
            pending_extractions=_list("pending_extractions"),
            raw=dict(data),
        )

    # ── Convenience accessors ────────────────────────────────────────────────

    @property
    def is_clear(self) -> bool:
        """True when no rule in the set raised a flag."""
        return not self.flags

    @property
    def critical_flags(self) -> list[RiskFlag]:
        """Flags at ``CRITICAL`` severity — the ones that should block onboarding."""
        return self.flags_at(RiskLevel.CRITICAL)

    @property
    def high_flags(self) -> list[RiskFlag]:
        """Flags at ``HIGH`` severity."""
        return self.flags_at(RiskLevel.HIGH)

    @property
    def is_partial(self) -> bool:
        """True when some data was unavailable, so the result is incomplete.

        A partial assessment is still usable, but an absent flag is not proof of
        a clean result: check :attr:`timed_out_services`, :attr:`failed_rules`
        and :attr:`pending_extractions` before treating it as a full screen.
        """
        return bool(self.timed_out_services or self.failed_rules or self.pending_extractions)

    def flags_at(self, *levels: RiskLevel) -> list[RiskFlag]:
        """Flags matching any of ``levels``, ordered as returned by the API."""
        wanted = set(levels)
        return [f for f in self.flags if f.severity in wanted]

    def flags_at_or_above(self, level: RiskLevel) -> list[RiskFlag]:
        """Flags at ``level`` or more severe.

        A flag whose severity this client version does not recognise is
        :attr:`RiskLevel.UNKNOWN`, which ranks above ``CRITICAL``, so it is always
        included. Its original string is on ``flag.raw``.
        """
        return [f for f in self.flags if f.severity.rank >= level.rank]

    def has_flag(self, code: str) -> bool:
        """True when a flag with ``code`` was raised, e.g. ``"ACCOUNTS_OVERDUE"``."""
        return any(f.code == code for f in self.flags)

    def flag(self, code: str) -> RiskFlag | None:
        """The flag with ``code``, or ``None`` when it was not raised."""
        return next((f for f in self.flags if f.code == code), None)

    def rules_with_status(self, status: RuleStatus) -> list[RuleResult]:
        """Every rule result matching ``status``."""
        return [r for r in self.rule_results if r.status == status]

    def __iter__(self) -> Iterator[RiskFlag]:
        """Iterating an assessment iterates its flags."""
        return iter(self.flags)

    def __len__(self) -> int:
        """The number of flags raised."""
        return len(self.flags)
