"""Screening sources: sanctions, adverse media, offshore leaks, GLEIF, insolvency."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .._transport import AsyncResource, SyncResource, _names_body, _seg

__all__ = [
    "AsyncGleif",
    "AsyncIndividualInsolvency",
    "AsyncNews",
    "AsyncOffshoreLeaks",
    "AsyncSanctions",
    "Gleif",
    "IndividualInsolvency",
    "News",
    "OffshoreLeaks",
    "Sanctions",
]

JSON = dict[str, Any]

#: Declared in the API schema for the batch sanctions and offshore-leaks endpoints.
MAX_SCREEN_NAMES = 500


def _entities_body(entities: Iterable[Mapping[str, Any]]) -> JSON:
    """Validate the ``{"entities": [{"key", "names"}]}`` body shape."""
    payload: list[JSON] = []
    for entity in entities:
        key = str(entity.get("key", "")).strip()
        names = [str(n).strip() for n in entity.get("names", []) if str(n).strip()]
        if not key:
            raise ValueError("each entity needs a non-empty 'key'")
        if not names:
            raise ValueError(f"entity {key!r} needs at least one name")
        payload.append({"key": key, "names": names})
    if not payload:
        raise ValueError("entities must contain at least one entry")
    return {"entities": payload}


def _entities_params(
    search: str | None,
    entity_type: str | None,
    sanctioned: bool | None,
    dataset: str | None,
    page: int | None,
    page_size: int | None,
) -> JSON:
    return {
        "search": search,
        "entity_type": entity_type,
        "sanctioned": sanctioned,
        "dataset": dataset,
        "page": page,
        "page_size": page_size,
    }


class Sanctions(SyncResource):
    """Screen names against OFAC, the UN Security Council, the UK Sanctions List and the EU FSF.

    Matching is approximate — these lists carry transliterated names, aliases and
    date-of-birth ranges — so treat every hit as a candidate for human review
    rather than a confirmed match.
    """

    def status(self) -> JSON:
        """Whether the screening dataset is loaded and ready."""
        return self._get("/sanctions/status")

    def meta(self) -> JSON:
        """Provenance of the loaded lists: sources, publication dates, record counts."""
        return self._get("/sanctions/meta")

    def screen(
        self,
        name: str,
        *,
        threshold: int | None = None,
        vector_threshold: float | None = None,
    ) -> JSON:
        """Screen a single name.

        Args:
            name: Person or organisation name to screen.
            threshold: Fuzzy-match threshold, an integer from 1 to 100. Overrides
                the server default; lower values return more, weaker candidates.
            vector_threshold: Vector-similarity threshold, from 0.0 to 1.0.
                Overrides the server default.
        """
        return self._get(
            "/sanctions/screen",
            params={"name": name, "threshold": threshold, "vector_threshold": vector_threshold},
        )

    def screen_names(self, names: Sequence[str]) -> JSON:
        """Screen up to 500 names in one request.

        Far cheaper than a loop over :meth:`screen`: one request against your
        rate limit instead of one per name.
        """
        return self._post(
            "/sanctions/screen-names", json=_names_body(names, limit=MAX_SCREEN_NAMES)
        )

    def entities(
        self,
        *,
        search: str | None = None,
        entity_type: str | None = None,
        sanctioned: bool | None = None,
        dataset: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> JSON:
        """Browse the underlying sanctions entities.

        Args:
            search: Substring filter on entity name.
            entity_type: e.g. ``"person"`` or ``"organization"``.
            sanctioned: Filter to currently-designated entities.
            dataset: Restrict to one source list, e.g. ``"gb_fcdo_sanctions"``.
        """
        return self._get(
            "/sanctions/entities",
            params=_entities_params(search, entity_type, sanctioned, dataset, page, page_size),
        )


class AsyncSanctions(AsyncResource):
    """Awaitable mirror of :class:`Sanctions`."""

    async def status(self) -> JSON:
        """Whether the screening dataset is loaded and ready."""
        return await self._get("/sanctions/status")

    async def meta(self) -> JSON:
        """Provenance of the loaded lists."""
        return await self._get("/sanctions/meta")

    async def screen(
        self,
        name: str,
        *,
        threshold: int | None = None,
        vector_threshold: float | None = None,
    ) -> JSON:
        """Screen a single name."""
        return await self._get(
            "/sanctions/screen",
            params={"name": name, "threshold": threshold, "vector_threshold": vector_threshold},
        )

    async def screen_names(self, names: Sequence[str]) -> JSON:
        """Screen up to 500 names in one request."""
        return await self._post(
            "/sanctions/screen-names", json=_names_body(names, limit=MAX_SCREEN_NAMES)
        )

    async def entities(
        self,
        *,
        search: str | None = None,
        entity_type: str | None = None,
        sanctioned: bool | None = None,
        dataset: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> JSON:
        """Browse the underlying sanctions entities."""
        return await self._get(
            "/sanctions/entities",
            params=_entities_params(search, entity_type, sanctioned, dataset, page, page_size),
        )


class News(SyncResource):
    """Adverse media search. **Requires an active Professional subscription.**

    Name matching against news results is noisy by nature, so a hit here is a
    lead to review, not a finding. In an assessment these only raise a
    low-severity ``ADVERSE_MEDIA_UNCONFIRMED`` flag until an analyst confirms the
    specific article.
    """

    def status(self) -> JSON:
        """Whether adverse media search is configured and available."""
        return self._get("/news/status")

    def search_names(self, names: Sequence[str]) -> JSON:
        """Search adverse media for a batch of names.

        The per-request cap is set server-side and can be tuned by the operator,
        so a large batch may be rejected with a 422.
        """
        return self._post("/news/search-names", json=_names_body(names))

    def search_entities(self, entities: Iterable[Mapping[str, Any]]) -> JSON:
        """Search adverse media for entities that each have several known names.

        Args:
            entities: Dicts of ``{"key": "...", "names": ["...", ...]}``. The key
                is yours to choose and is echoed back on the results, so use it to
                join hits onto your own records.
        """
        return self._post("/news/search-entities", json=_entities_body(entities))

    def screen_company(self, company_number: str) -> JSON:
        """Search adverse media for a company and its officers and PSCs."""
        return self._get(
            "/news/screen-company",
            params={"company_number": _seg(company_number, "company_number")},
        )


class AsyncNews(AsyncResource):
    """Awaitable mirror of :class:`News`."""

    async def status(self) -> JSON:
        """Whether adverse media search is configured and available."""
        return await self._get("/news/status")

    async def search_names(self, names: Sequence[str]) -> JSON:
        """Search adverse media for a batch of names."""
        return await self._post("/news/search-names", json=_names_body(names))

    async def search_entities(self, entities: Iterable[Mapping[str, Any]]) -> JSON:
        """Search adverse media for entities that each have several known names."""
        return await self._post("/news/search-entities", json=_entities_body(entities))

    async def screen_company(self, company_number: str) -> JSON:
        """Search adverse media for a company and its officers and PSCs."""
        return await self._get(
            "/news/screen-company",
            params={"company_number": _seg(company_number, "company_number")},
        )


class OffshoreLeaks(SyncResource):
    """Screen against the ICIJ Offshore Leaks database.

    Covers the Panama, Paradise and Pandora Papers and the Offshore Leaks and
    Bahamas Leaks datasets. As with adverse media, matches are name-based and
    unconfirmed hits only raise a low-severity flag in an assessment.
    """

    def status(self) -> JSON:
        """Whether the Offshore Leaks dataset is available."""
        return self._get("/offshore-leaks/status")

    def screen_names(self, names: Sequence[str]) -> JSON:
        """Screen up to 500 names against the leaks datasets."""
        return self._post(
            "/offshore-leaks/screen-names", json=_names_body(names, limit=MAX_SCREEN_NAMES)
        )

    def screen_company(self, company_number: str) -> JSON:
        """Screen a company and its officers and PSCs against the leaks datasets."""
        return self._get(
            "/offshore-leaks/screen-company",
            params={"company_number": _seg(company_number, "company_number")},
        )

    def node(
        self,
        node_id: str,
        *,
        name: str | None = None,
        node_type: str | None = None,
    ) -> JSON:
        """Fetch one leaks node — an entity, officer, intermediary or address.

        Args:
            node_id: ICIJ node id, as returned on a screening match.
            name: Expected name, used to disambiguate when the id is ambiguous.
            node_type: Expected node type, used the same way.
        """
        return self._get(
            f"/offshore-leaks/node/{_seg(node_id, 'node_id')}",
            params={"name": name, "node_type": node_type},
        )


class AsyncOffshoreLeaks(AsyncResource):
    """Awaitable mirror of :class:`OffshoreLeaks`."""

    async def status(self) -> JSON:
        """Whether the Offshore Leaks dataset is available."""
        return await self._get("/offshore-leaks/status")

    async def screen_names(self, names: Sequence[str]) -> JSON:
        """Screen up to 500 names against the leaks datasets."""
        return await self._post(
            "/offshore-leaks/screen-names", json=_names_body(names, limit=MAX_SCREEN_NAMES)
        )

    async def screen_company(self, company_number: str) -> JSON:
        """Screen a company and its officers and PSCs against the leaks datasets."""
        return await self._get(
            "/offshore-leaks/screen-company",
            params={"company_number": _seg(company_number, "company_number")},
        )

    async def node(
        self,
        node_id: str,
        *,
        name: str | None = None,
        node_type: str | None = None,
    ) -> JSON:
        """Fetch one leaks node."""
        return await self._get(
            f"/offshore-leaks/node/{_seg(node_id, 'node_id')}",
            params={"name": name, "node_type": node_type},
        )


class Gleif(SyncResource):
    """Global LEI Foundation lookups — legal entity identifiers and parent chains."""

    def company(self, company_number: str) -> JSON:
        """The company's LEI record and its direct and ultimate parents."""
        return self._get(
            "/gleif/company", params={"company_number": _seg(company_number, "company_number")}
        )


class AsyncGleif(AsyncResource):
    """Awaitable mirror of :class:`Gleif`."""

    async def company(self, company_number: str) -> JSON:
        """The company's LEI record and its parents."""
        return await self._get(
            "/gleif/company", params={"company_number": _seg(company_number, "company_number")}
        )


class IndividualInsolvency(SyncResource):
    """Insolvency Service Individual Insolvency Register screening."""

    def screen_company(self, company_number: str) -> JSON:
        """Check a company's officers and PSCs for personal insolvency records."""
        return self._get(
            "/individual-insolvency/screen-company",
            params={"company_number": _seg(company_number, "company_number")},
        )


class AsyncIndividualInsolvency(AsyncResource):
    """Awaitable mirror of :class:`IndividualInsolvency`."""

    async def screen_company(self, company_number: str) -> JSON:
        """Check a company's officers and PSCs for personal insolvency records."""
        return await self._get(
            "/individual-insolvency/screen-company",
            params={"company_number": _seg(company_number, "company_number")},
        )
