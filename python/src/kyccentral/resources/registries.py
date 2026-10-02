"""Sector registries and jurisdiction reference data."""

from __future__ import annotations

from typing import Any

from .._transport import AsyncResource, SyncResource, _seg

__all__ = [
    "AsyncCharity",
    "AsyncHmrcVat",
    "AsyncJurisdictions",
    "AsyncOffshoreJurisdictions",
    "Charity",
    "HmrcVat",
    "Jurisdictions",
    "OffshoreJurisdictions",
]

JSON = dict[str, Any]


class Charity(SyncResource):
    """Charity Commission for England and Wales lookups."""

    def status(self) -> JSON:
        """Whether Charity Commission access is configured."""
        return self._get("/charity/status")

    def search(self, q: str) -> JSON:
        """Search registered charities by name."""
        return self._get("/charity/search", params={"q": q})

    def get(self, registration_number: str, *, suffix: int | None = None) -> JSON:
        """A charity's register entry.

        Args:
            registration_number: Charity registration number.
            suffix: Linked-charity suffix, an integer. Defaults to 0, the main
                charity.
        """
        return self._get(
            f"/charity/charity/{_seg(registration_number, 'registration_number')}",
            params={"suffix": suffix},
        )

    def trustees(self, registration_number: str) -> JSON:
        """The charity's registered trustees."""
        return self._get(
            f"/charity/charity/{_seg(registration_number, 'registration_number')}/trustees"
        )


class AsyncCharity(AsyncResource):
    """Awaitable mirror of :class:`Charity`."""

    async def status(self) -> JSON:
        """Whether Charity Commission access is configured."""
        return await self._get("/charity/status")

    async def search(self, q: str) -> JSON:
        """Search registered charities by name."""
        return await self._get("/charity/search", params={"q": q})

    async def get(self, registration_number: str, *, suffix: int | None = None) -> JSON:
        """A charity's register entry."""
        return await self._get(
            f"/charity/charity/{_seg(registration_number, 'registration_number')}",
            params={"suffix": suffix},
        )

    async def trustees(self, registration_number: str) -> JSON:
        """The charity's registered trustees."""
        return await self._get(
            f"/charity/charity/{_seg(registration_number, 'registration_number')}/trustees"
        )


class HmrcVat(SyncResource):
    """HMRC VAT registration lookups."""

    def status(self) -> JSON:
        """Whether HMRC VAT lookups are configured."""
        return self._get("/hmrc-vat/status")

    def check(self, vat_number: str) -> JSON:
        """Check a UK VAT registration number.

        Args:
            vat_number: VAT number, with or without the ``GB`` prefix.
        """
        return self._get("/hmrc-vat/check", params={"vat_number": vat_number})


class AsyncHmrcVat(AsyncResource):
    """Awaitable mirror of :class:`HmrcVat`."""

    async def status(self) -> JSON:
        """Whether HMRC VAT lookups are configured."""
        return await self._get("/hmrc-vat/status")

    async def check(self, vat_number: str) -> JSON:
        """Check a UK VAT registration number."""
        return await self._get("/hmrc-vat/check", params={"vat_number": vat_number})


class Jurisdictions(SyncResource):
    """FATF high-risk and increased-monitoring jurisdiction reference data.

    Updated after each FATF plenary (roughly February, June and October).
    """

    def list(self) -> Any:
        """The current FATF black list and grey list."""
        return self._get("/jurisdictions")

    def check(self, country: str) -> JSON:
        """Whether one country is FATF-listed, and on which list."""
        return self._get("/jurisdictions/check", params={"country": country})


class AsyncJurisdictions(AsyncResource):
    """Awaitable mirror of :class:`Jurisdictions`."""

    async def list(self) -> Any:
        """The current FATF black list and grey list."""
        return await self._get("/jurisdictions")

    async def check(self, country: str) -> JSON:
        """Whether one country is FATF-listed, and on which list."""
        return await self._get("/jurisdictions/check", params={"country": country})


class OffshoreJurisdictions(SyncResource):
    """Offshore and shell-company jurisdiction reference data."""

    def list(self) -> Any:
        """Known offshore jurisdictions and the keywords used to detect them."""
        return self._get("/offshore-jurisdictions")

    def check(self, name: str) -> JSON:
        """Whether a name or address indicates an offshore jurisdiction."""
        return self._get("/offshore-jurisdictions/check", params={"name": name})


class AsyncOffshoreJurisdictions(AsyncResource):
    """Awaitable mirror of :class:`OffshoreJurisdictions`."""

    async def list(self) -> Any:
        """Known offshore jurisdictions and their detection keywords."""
        return await self._get("/offshore-jurisdictions")

    async def check(self, name: str) -> JSON:
        """Whether a name or address indicates an offshore jurisdiction."""
        return await self._get("/offshore-jurisdictions/check", params={"name": name})
