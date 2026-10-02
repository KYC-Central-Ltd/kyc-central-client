"""AI analysis endpoints and the product documentation assistant."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .._transport import AsyncResource, SyncResource, _charge_key, _resolve_ai_timeout

__all__ = ["Analysis", "AsyncAnalysis", "AsyncDocs", "Docs"]

JSON = dict[str, Any]

_FILING_EXTRACT_MODES = ("extract", "verify")


def _company_body(
    company_number: str,
    rule_set_id: str | None,
    provider: str | None,
    sections: Sequence[str] | None,
    fca_frn: str | None,
    context: Mapping[str, Any] | None,
) -> JSON:
    body: JSON = {"company_number": company_number}
    if rule_set_id is not None:
        body["rule_set_id"] = rule_set_id
    if provider is not None:
        body["provider"] = provider
    if sections:
        section_list = list(sections)
        if len(section_list) > 50:
            raise ValueError(f"sections accepts at most 50 entries, got {len(section_list)}")
        body["sections"] = section_list
    if fca_frn is not None:
        body["fca_frn"] = fca_frn
    if context is not None:
        body["context"] = dict(context)
    return body


def _filing_extract_body(
    company_number: str, transaction_id: str, mode: str, provider: str | None
) -> JSON:
    if mode not in _FILING_EXTRACT_MODES:
        raise ValueError(f"mode must be one of {_FILING_EXTRACT_MODES}, got {mode!r}")
    body: JSON = {
        "company_number": company_number,
        "transaction_id": transaction_id,
        "mode": mode,
    }
    if provider is not None:
        body["provider"] = provider
    return body


def _charge_registration_body(company_number: str, charge_key: str, provider: str | None) -> JSON:
    body: JSON = {"company_number": company_number, "charge_key": _charge_key(charge_key)}
    if provider is not None:
        body["provider"] = provider
    return body


def _docs_body(message: str, history: Iterable[Mapping[str, Any]] | None) -> JSON:
    if not message or not message.strip():
        raise ValueError("message must be a non-empty string")
    body: JSON = {"message": message}
    if history:
        turns = [dict(turn) for turn in history]
        if len(turns) > 12:
            raise ValueError(f"history accepts at most 12 turns, got {len(turns)}")
        body["history"] = turns
    return body


class Analysis(SyncResource):
    """LLM-written analyst commentary over an assessment.

    **Requires an active Professional subscription**, except for :meth:`status`.
    These calls invoke a language model, so they are slower and more expensive
    than the deterministic rule engine — and, like any LLM output, the narrative
    is a drafting aid for an analyst, not a compliance decision.
    """

    def status(self) -> JSON:
        """Which AI providers are configured. Available without a subscription."""
        return self._get("/analysis/status")

    def company(
        self,
        company_number: str,
        *,
        rule_set_id: str | None = None,
        provider: str | None = None,
        sections: Sequence[str] | None = None,
        fca_frn: str | None = None,
        context: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Write a narrative risk analysis for one company.

        Args:
            company_number: Companies House number to analyse.
            rule_set_id: Rule set whose findings should frame the analysis.
            provider: Override the AI provider, e.g. ``"claude"``, ``"gpt"``,
                ``"gemini"``. Defaults to whichever the API is configured with.
            sections: Restrict the write-up to named sections. At most 50.
            fca_frn: FCA Firm Reference Number, when the company is regulated and
                you already know it.
            context: Evidence gathered elsewhere — confirmed screening hits,
                selected filings, analyst-confirmed identity links — folded into
                the prompt so the analysis reflects your review rather than the
                raw unconfirmed matches.
            timeout: Seconds to wait for this call. Defaults to 120, or the
                client's timeout if that is longer. POSTs are never re-sent after
                a timeout, so a slow call is not billed twice.
        """
        return self._post(
            "/analysis/company",
            json=_company_body(company_number, rule_set_id, provider, sections, fca_frn, context),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )

    def adverse_media_overview(
        self,
        company_number: str,
        *,
        provider: str | None = None,
        results: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Summarise adverse media results into a short overview.

        Args:
            results: Search results to summarise, as returned by
                ``client.news.screen_company()`` or ``client.news.search_names()``.
            timeout: Seconds to wait for this call. Defaults to 120, or the
                client's timeout if that is longer. POSTs are never re-sent after
                a timeout, so a slow call is not billed twice.
        """
        body: JSON = {"company_number": company_number}
        if provider is not None:
            body["provider"] = provider
        if results is not None:
            body["results"] = dict(results)
        return self._post(
            "/analysis/adverse-media-overview",
            json=body,
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )

    def filing_extract(
        self,
        company_number: str,
        transaction_id: str,
        *,
        mode: str = "extract",
        provider: str | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Read a filing PDF with an LLM.

        Args:
            mode: ``"extract"`` to pull structured data out of the filing, or
                ``"verify"`` to check an existing extraction against the document.
            timeout: Seconds to wait for this call. Defaults to 120, or the
                client's timeout if that is longer. POSTs are never re-sent after
                a timeout, so a slow call is not billed twice.
        """
        return self._post(
            "/analysis/filing-extract",
            json=_filing_extract_body(company_number, transaction_id, mode, provider),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )

    def charge_registration(
        self,
        company_number: str,
        charge_key: str,
        *,
        provider: str | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Read a charge's "Registration of a charge" form with a vision-capable LLM.

        For forms with no text layer (paper and pre-2013 filings) — the case
        ``companies.extract_charge_registration`` answers with ``needs_ai``.
        Returns the same merged record, with source ``"ai_vision"``; an
        unreadable form returns ``{"available": false, "reason": ...}``. Spends
        AI credits on first use; a repeat call for the same charge is served from
        the stored record.

        Args:
            charge_key: The charge code, or ``"{company_number}-{charge_number}"``
                for pre-2013 charges.
            timeout: Seconds to wait for this call. Defaults to 120, or the
                client's timeout if that is longer. POSTs are never re-sent after
                a timeout, so a slow call is not billed twice.

        Raises:
            ValueError: ``charge_key`` is blank.
        """
        return self._post(
            "/analysis/charge-registration",
            json=_charge_registration_body(company_number, charge_key, provider),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )


class AsyncAnalysis(AsyncResource):
    """Awaitable mirror of :class:`Analysis`."""

    async def status(self) -> JSON:
        """Which AI providers are configured."""
        return await self._get("/analysis/status")

    async def company(
        self,
        company_number: str,
        *,
        rule_set_id: str | None = None,
        provider: str | None = None,
        sections: Sequence[str] | None = None,
        fca_frn: str | None = None,
        context: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Write a narrative risk analysis for one company."""
        return await self._post(
            "/analysis/company",
            json=_company_body(company_number, rule_set_id, provider, sections, fca_frn, context),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )

    async def adverse_media_overview(
        self,
        company_number: str,
        *,
        provider: str | None = None,
        results: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Summarise adverse media results into a short overview."""
        body: JSON = {"company_number": company_number}
        if provider is not None:
            body["provider"] = provider
        if results is not None:
            body["results"] = dict(results)
        return await self._post(
            "/analysis/adverse-media-overview",
            json=body,
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )

    async def filing_extract(
        self,
        company_number: str,
        transaction_id: str,
        *,
        mode: str = "extract",
        provider: str | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Read a filing PDF with an LLM."""
        return await self._post(
            "/analysis/filing-extract",
            json=_filing_extract_body(company_number, transaction_id, mode, provider),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )

    async def charge_registration(
        self,
        company_number: str,
        charge_key: str,
        *,
        provider: str | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Read a charge's "Registration of a charge" form with a vision-capable LLM."""
        return await self._post(
            "/analysis/charge-registration",
            json=_charge_registration_body(company_number, charge_key, provider),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )


class Docs(SyncResource):
    """Ask questions about the product in natural language."""

    def ask(
        self,
        message: str,
        *,
        history: Iterable[Mapping[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Ask the documentation assistant a question.

        Args:
            message: The question. Up to 2,000 characters.
            history: Prior turns for follow-up questions, at most 12, each
                ``{"role": "user"|"assistant", "content": "..."}``.
            timeout: Seconds to wait for this call. Defaults to 120, or the
                client's timeout if that is longer. POSTs are never re-sent after
                a timeout, so a slow call is not billed twice.
        """
        return self._post(
            "/docs/ask",
            json=_docs_body(message, history),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )


class AsyncDocs(AsyncResource):
    """Awaitable mirror of :class:`Docs`."""

    async def ask(
        self,
        message: str,
        *,
        history: Iterable[Mapping[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        """Ask the documentation assistant a question."""
        return await self._post(
            "/docs/ask",
            json=_docs_body(message, history),
            timeout=_resolve_ai_timeout(self._transport.config.timeout, timeout),
        )
