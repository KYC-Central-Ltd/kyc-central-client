"""Full report data as JSON."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .._transport import AsyncResource, SyncResource, _resolve_ai_timeout

__all__ = ["AsyncReports", "Reports"]

JSON = dict[str, Any]


def _comma_joined(value: str | Sequence[str] | None) -> str | None:
    """A list becomes one comma-joined string; a plain string passes through."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    items = list(value)
    return ",".join(items) if items else None


def _report_data_body(
    company_number: str,
    sections: str | Sequence[str] | None,
    rule_set_ids: str | Sequence[str] | None,
    ai_provider: str | None,
    fca_frn: str | None,
    context: Mapping[str, Any] | None,
) -> JSON:
    body: JSON = {"company_number": company_number}
    joined_sections = _comma_joined(sections)
    if joined_sections is not None:
        body["sections"] = joined_sections
    joined_rule_sets = _comma_joined(rule_set_ids)
    if joined_rule_sets is not None:
        body["rule_set_ids"] = joined_rule_sets
    if ai_provider is not None:
        body["ai_provider"] = ai_provider
    if fca_frn is not None:
        body["fca_frn"] = fca_frn
    if context is not None:
        body["context"] = dict(context)
    return body


class Reports(SyncResource):
    """The full report as JSON rather than a PDF. **Requires an API key.**"""

    def data(
        self,
        company_number: str,
        *,
        sections: str | Sequence[str] | None = None,
        rule_set_ids: str | Sequence[str] | None = None,
        ai_provider: str | None = None,
        fca_frn: str | None = None,
        context: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """The full report as JSON instead of a PDF.

        The assessment, flags per rule set and every section's data. Requires an
        API key and uses one PDF report credit (a subscriber's monthly allowance
        first, then purchased credits).

        Args:
            company_number: Companies House number to report on.
            sections: Any of ``assessment``, ``company_data``, ``filings``,
                ``disqualifications``, ``fca``, ``gleif``,
                ``individual_insolvency``, ``confirmation_statements``,
                ``sanctions``, ``adverse_media``, ``ai_analysis``,
                ``offshore_leaks``. Defaults to ``assessment``, ``company_data``,
                ``sanctions``. Leave out ``ai_analysis`` for a report with no
                AI-written content. A list is sent comma-joined.
            rule_set_ids: Rule sets to run; their rules are combined and
                deduplicated. A list is sent comma-joined.
            ai_provider: Override the AI provider.
            fca_frn: A confirmed FCA firm reference number. Once given, the FCA
                lookup becomes a required check.
            context: The analyst's confirmations. Its ``accepted_gaps`` (with
                ``accepted_gaps_at``, no more than 24 hours old) lists
                ``sanctions`` / ``adverse_media`` / ``offshore_leaks`` checks to
                proceed without if they are unavailable; those come back under
                ``generated_without``.
            timeout: Seconds to wait for this call. Defaults to 120, or the
                client's timeout if that is longer.

        Raises:
            ~kyccentral.errors.ServiceUnavailableError: A required check was
                unavailable. A report is never returned with a required check
                missing: that is a 503 with ``Retry-After`` (about five minutes)
                and the credit is returned. The client does not retry it; wait
                for the error's ``retry_after`` and call again.
        """
        return self._post(
            "/billing/report-data",
            json=_report_data_body(
                company_number, sections, rule_set_ids, ai_provider, fca_frn, context
            ),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )


class AsyncReports(AsyncResource):
    """Awaitable mirror of :class:`Reports`."""

    async def data(
        self,
        company_number: str,
        *,
        sections: str | Sequence[str] | None = None,
        rule_set_ids: str | Sequence[str] | None = None,
        ai_provider: str | None = None,
        fca_frn: str | None = None,
        context: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """The full report as JSON instead of a PDF."""
        return await self._post(
            "/billing/report-data",
            json=_report_data_body(
                company_number, sections, rule_set_ids, ai_provider, fca_frn, context
            ),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )
