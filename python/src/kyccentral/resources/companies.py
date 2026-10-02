"""Companies House company, officer, PSC, charge and filing data."""

from __future__ import annotations

from typing import Any

from .._transport import AsyncResource, SyncResource, _charge_key, _seg

__all__ = ["AsyncCompanies", "Companies"]

JSON = dict[str, Any]


def _search_params(items_per_page: int | None, start_index: int | None) -> JSON:
    return {"items_per_page": items_per_page, "start_index": start_index}


def _charge_registration_body(charge_key: str) -> JSON:
    return {"charge_key": _charge_key(charge_key)}


def _advanced_search_params(
    company_name_includes: str | None,
    company_name_excludes: str | None,
    company_status: str | None,
    company_type: str | None,
    location: str | None,
    sic_codes: str | None,
    incorporated_from: str | None,
    incorporated_to: str | None,
    dissolved_from: str | None,
    dissolved_to: str | None,
    size: int | None,
    start_index: int | None,
    items_per_page: int | None,
) -> JSON:
    return {
        "company_name_includes": company_name_includes,
        "company_name_excludes": company_name_excludes,
        "company_status": company_status,
        "company_type": company_type,
        "location": location,
        "sic_codes": sic_codes,
        "incorporated_from": incorporated_from,
        "incorporated_to": incorporated_to,
        "dissolved_from": dissolved_from,
        "dissolved_to": dissolved_to,
        "size": size,
        "start_index": start_index,
        "items_per_page": items_per_page,
    }


class Companies(SyncResource):
    """Company registry lookups. Available on every plan.

    Company numbers are Companies House registration numbers — up to eight
    alphanumeric characters, e.g. ``"00445790"`` or ``"SC123456"``. Leading
    zeroes are significant.
    """

    def search(
        self,
        q: str,
        *,
        items_per_page: int | None = None,
        start_index: int | None = None,
    ) -> JSON:
        """Search companies by name or number.

        Args:
            q: Free-text query — a company name, or a registration number.
            items_per_page: Page size. The API applies its own default and cap.
            start_index: Zero-based offset for paging.
        """
        return self._get(
            "/companies/search", params={"q": q, **_search_params(items_per_page, start_index)}
        )

    def search_officers(
        self,
        q: str,
        *,
        items_per_page: int | None = None,
        start_index: int | None = None,
    ) -> JSON:
        """Search officers (directors, secretaries) by name across all companies."""
        return self._get(
            "/companies/search/officers",
            params={"q": q, **_search_params(items_per_page, start_index)},
        )

    def advanced_search(
        self,
        *,
        company_name_includes: str | None = None,
        company_name_excludes: str | None = None,
        company_status: str | None = None,
        company_type: str | None = None,
        location: str | None = None,
        sic_codes: str | None = None,
        incorporated_from: str | None = None,
        incorporated_to: str | None = None,
        dissolved_from: str | None = None,
        dissolved_to: str | None = None,
        size: int | None = None,
        start_index: int | None = None,
        items_per_page: int | None = None,
    ) -> JSON:
        """Structured company search with status, type, SIC and date filters.

        Dates are ``YYYY-MM-DD``. Each of ``company_status``, ``company_type``
        and ``sic_codes`` takes a single value, matched exactly.
        """
        return self._get(
            "/companies/advanced-search",
            params=_advanced_search_params(
                company_name_includes,
                company_name_excludes,
                company_status,
                company_type,
                location,
                sic_codes,
                incorporated_from,
                incorporated_to,
                dissolved_from,
                dissolved_to,
                size,
                start_index,
                items_per_page,
            ),
        )

    def get(self, company_number: str) -> JSON:
        """The company profile: name, status, type, dates, address, SIC codes."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}")

    def dossier(self, company_number: str) -> JSON:
        """Profile, officers, PSCs, charges, insolvency and filings in one call.

        Cheaper than issuing each lookup separately when you need the full
        picture — one request against your rate limit instead of six.
        """
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/dossier")

    def officers(self, company_number: str) -> JSON:
        """Appointed officers, including resigned ones."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/officers")

    def officer_company_matches(self, company_number: str) -> JSON:
        """Suggest which registered company each unidentified corporate officer might be.

        Returns ``{"matches": {officer_name: [candidate, ...]}}``. Suggestions
        only, for a human to review; confirm one by passing
        ``confirmed_officer_company_links`` to ``kyc.assess``.
        """
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}/officer-company-matches"
        )

    def persons_with_significant_control(self, company_number: str) -> JSON:
        """Registered beneficial owners (PSCs)."""
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}/persons-with-significant-control"
        )

    #: Shorthand for :meth:`persons_with_significant_control`.
    pscs = persons_with_significant_control

    def psc_statements(self, company_number: str) -> JSON:
        """PSC statements — the register's explanations for an absent PSC."""
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            "/persons-with-significant-control-statements"
        )

    def psc_chain_depth(self, company_number: str) -> JSON:
        """How many corporate layers sit between the company and a real person."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/psc-chain-depth")

    def psc_chain_tree(self, company_number: str) -> JSON:
        """The full ownership chain as a tree, resolving corporate PSCs upwards."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/psc-chain-tree")

    def charges(self, company_number: str) -> JSON:
        """Registered charges (secured debt) against the company."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/charges")

    def charge(self, company_number: str, charge_id: str) -> JSON:
        """One charge in full, including the persons entitled to it."""
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            f"/charges/{_seg(charge_id, 'charge_id')}"
        )

    def charge_registrations(self, company_number: str) -> JSON:
        """Charge registration records already extracted for this company.

        Returns ``{"items": [...]}``: the full charge-holder list and
        level-of-influence signals for each. Empty until
        ``extract_charge_registration`` has been run.
        """
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}/charges/registrations"
        )

    def insolvency(self, company_number: str) -> JSON:
        """Insolvency cases. Returns an empty payload when there are none."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/insolvency")

    def disqualifications(self, company_number: str) -> JSON:
        """Disqualified-director records across the company's officers."""
        return self._get(f"/companies/{_seg(company_number, 'company_number')}/disqualifications")

    def officer_disqualification(self, company_number: str, officer_id: str) -> JSON:
        """Disqualification record for one officer of this company."""
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            f"/officers/{_seg(officer_id, 'officer_id')}/disqualification"
        )

    def officer_appointments(
        self,
        officer_id: str,
        *,
        items_per_page: int | None = None,
        start_index: int | None = None,
    ) -> JSON:
        """Every appointment held by one officer, across all companies."""
        return self._get(
            f"/companies/officers/{_seg(officer_id, 'officer_id')}/appointments",
            params=_search_params(items_per_page, start_index),
        )

    # ── Professional plan ────────────────────────────────────────────────────

    def filing_history(
        self,
        company_number: str,
        *,
        start_index: int | None = None,
        items_per_page: int | None = None,
        category: str | None = None,
    ) -> JSON:
        """Filing history. **Requires an active Professional subscription.**

        Args:
            category: Companies House filing category, e.g. ``"accounts"``,
                ``"confirmation-statement"``, ``"officers"``.
        """
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}/filing-history",
            params={
                "start_index": start_index,
                "items_per_page": items_per_page,
                "category": category,
            },
        )

    def filing_extract(self, company_number: str, transaction_id: str) -> JSON:
        """Structured data parsed out of one filing.

        **Requires an active Professional subscription.**
        """
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            f"/filing-history/{_seg(transaction_id, 'transaction_id')}/extract"
        )

    def statement_of_capital(self, company_number: str) -> JSON:
        """Share capital and shareholders from the latest confirmation statement.

        **Requires an active Professional subscription.**
        """
        return self._get(
            f"/companies/{_seg(company_number, 'company_number')}/statement-of-capital"
        )

    def extract_charge_registration(self, company_number: str, charge_key: str) -> JSON:
        """Extract the full charge-holder list and level-of-influence signals for one charge.

        **Requires an active Professional subscription.** Spends no AI credits.

        ``charge_key`` is the charge code (e.g. ``"094462310004"``), or
        ``"{company_number}-{charge_number}"`` for pre-2013 charges. Paper and
        pre-2013 forms have no text layer; the response is then
        ``{"needs_ai": true, "charge_key", "filing_transaction_id"}`` and
        ``analysis.charge_registration`` can read the form instead.

        Raises:
            ValueError: ``charge_key`` is blank.
        """
        return self._post(
            f"/companies/{_seg(company_number, 'company_number')}/charges/registration",
            json=_charge_registration_body(charge_key),
        )


class AsyncCompanies(AsyncResource):
    """Awaitable mirror of :class:`Companies`. See there for full documentation."""

    async def search(
        self,
        q: str,
        *,
        items_per_page: int | None = None,
        start_index: int | None = None,
    ) -> JSON:
        """Search companies by name or number."""
        return await self._get(
            "/companies/search", params={"q": q, **_search_params(items_per_page, start_index)}
        )

    async def search_officers(
        self,
        q: str,
        *,
        items_per_page: int | None = None,
        start_index: int | None = None,
    ) -> JSON:
        """Search officers by name across all companies."""
        return await self._get(
            "/companies/search/officers",
            params={"q": q, **_search_params(items_per_page, start_index)},
        )

    async def advanced_search(
        self,
        *,
        company_name_includes: str | None = None,
        company_name_excludes: str | None = None,
        company_status: str | None = None,
        company_type: str | None = None,
        location: str | None = None,
        sic_codes: str | None = None,
        incorporated_from: str | None = None,
        incorporated_to: str | None = None,
        dissolved_from: str | None = None,
        dissolved_to: str | None = None,
        size: int | None = None,
        start_index: int | None = None,
        items_per_page: int | None = None,
    ) -> JSON:
        """Structured company search with status, type, SIC and date filters."""
        return await self._get(
            "/companies/advanced-search",
            params=_advanced_search_params(
                company_name_includes,
                company_name_excludes,
                company_status,
                company_type,
                location,
                sic_codes,
                incorporated_from,
                incorporated_to,
                dissolved_from,
                dissolved_to,
                size,
                start_index,
                items_per_page,
            ),
        )

    async def get(self, company_number: str) -> JSON:
        """The company profile."""
        return await self._get(f"/companies/{_seg(company_number, 'company_number')}")

    async def dossier(self, company_number: str) -> JSON:
        """Profile, officers, PSCs, charges, insolvency and filings in one call."""
        return await self._get(f"/companies/{_seg(company_number, 'company_number')}/dossier")

    async def officers(self, company_number: str) -> JSON:
        """Appointed officers, including resigned ones."""
        return await self._get(f"/companies/{_seg(company_number, 'company_number')}/officers")

    async def officer_company_matches(self, company_number: str) -> JSON:
        """Suggest which registered company each unidentified corporate officer might be."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/officer-company-matches"
        )

    async def persons_with_significant_control(self, company_number: str) -> JSON:
        """Registered beneficial owners (PSCs)."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/persons-with-significant-control"
        )

    #: Shorthand for :meth:`persons_with_significant_control`.
    pscs = persons_with_significant_control

    async def psc_statements(self, company_number: str) -> JSON:
        """PSC statements — the register's explanations for an absent PSC."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            "/persons-with-significant-control-statements"
        )

    async def psc_chain_depth(self, company_number: str) -> JSON:
        """How many corporate layers sit between the company and a real person."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/psc-chain-depth"
        )

    async def psc_chain_tree(self, company_number: str) -> JSON:
        """The full ownership chain as a tree."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/psc-chain-tree"
        )

    async def charges(self, company_number: str) -> JSON:
        """Registered charges (secured debt) against the company."""
        return await self._get(f"/companies/{_seg(company_number, 'company_number')}/charges")

    async def charge(self, company_number: str, charge_id: str) -> JSON:
        """One charge in full, including the persons entitled to it."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            f"/charges/{_seg(charge_id, 'charge_id')}"
        )

    async def charge_registrations(self, company_number: str) -> JSON:
        """Charge registration records already extracted for this company."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/charges/registrations"
        )

    async def insolvency(self, company_number: str) -> JSON:
        """Insolvency cases. Returns an empty payload when there are none."""
        return await self._get(f"/companies/{_seg(company_number, 'company_number')}/insolvency")

    async def disqualifications(self, company_number: str) -> JSON:
        """Disqualified-director records across the company's officers."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/disqualifications"
        )

    async def officer_disqualification(self, company_number: str, officer_id: str) -> JSON:
        """Disqualification record for one officer of this company."""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            f"/officers/{_seg(officer_id, 'officer_id')}/disqualification"
        )

    async def officer_appointments(
        self,
        officer_id: str,
        *,
        items_per_page: int | None = None,
        start_index: int | None = None,
    ) -> JSON:
        """Every appointment held by one officer, across all companies."""
        return await self._get(
            f"/companies/officers/{_seg(officer_id, 'officer_id')}/appointments",
            params=_search_params(items_per_page, start_index),
        )

    async def filing_history(
        self,
        company_number: str,
        *,
        start_index: int | None = None,
        items_per_page: int | None = None,
        category: str | None = None,
    ) -> JSON:
        """Filing history. **Requires an active Professional subscription.**"""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/filing-history",
            params={
                "start_index": start_index,
                "items_per_page": items_per_page,
                "category": category,
            },
        )

    async def filing_extract(self, company_number: str, transaction_id: str) -> JSON:
        """Structured data parsed out of one filing. **Professional plan.**"""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}"
            f"/filing-history/{_seg(transaction_id, 'transaction_id')}/extract"
        )

    async def statement_of_capital(self, company_number: str) -> JSON:
        """Share capital and shareholders. **Professional plan.**"""
        return await self._get(
            f"/companies/{_seg(company_number, 'company_number')}/statement-of-capital"
        )

    async def extract_charge_registration(self, company_number: str, charge_key: str) -> JSON:
        """Extract the full charge-holder list and level-of-influence signals for one charge.

        **Professional plan.**
        """
        return await self._post(
            f"/companies/{_seg(company_number, 'company_number')}/charges/registration",
            json=_charge_registration_body(charge_key),
        )
