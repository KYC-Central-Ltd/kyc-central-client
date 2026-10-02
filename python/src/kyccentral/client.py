"""The blocking and awaitable client entry points."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any

import httpx

from . import resources as _r
from ._transport import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    AsyncTransport,
    ClientConfig,
    SyncTransport,
)

__all__ = ["AsyncKYCCentral", "KYCCentral"]

JSON = dict[str, Any]


class KYCCentral:
    """Blocking client for the KYC Central API.

    Args:
        api_key: Your API key. Falls back to the ``KYCCENTRAL_API_KEY``
            environment variable. May be omitted entirely: most reference and
            lookup endpoints work anonymously at a lower rate limit, but
            :meth:`~kyccentral.resources.kyc.Kyc.assess` and the AI endpoints
            always need a key.
        base_url: API root. Falls back to ``KYCCENTRAL_BASE_URL``, then to
            production.
        timeout: Per-request timeout in seconds. Ignored when ``http_client`` is
            supplied; configure the timeout on that client. The per-call
            ``timeout`` on the AI endpoints still applies.
        max_retries: Retries for timeouts, connection failures and retryable
            statuses (408, 429, 500, 502, 503, 504). Backoff is exponential with
            jitter and honours ``Retry-After``. Set to ``0`` to disable.
        http_client: Bring your own :class:`httpx.Client` — for a shared
            connection pool, a proxy, or custom TLS. You own its lifecycle; the
            client will not close it.
        default_headers: Extra headers on every request.

    Example:
        >>> from kyccentral import KYCCentral
        >>> with KYCCentral(api_key="...") as client:
        ...     assessment = client.kyc.assess("00445790")
        ...     print(assessment.risk_level, len(assessment.flags))
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._config = ClientConfig.resolve(
            api_key, base_url, timeout, max_retries, default_headers
        )
        self._transport = SyncTransport(self._config, http_client)

        #: Companies House company, officer, PSC, charge and filing data.
        self.companies = _r.Companies(self._transport)
        #: Run risk assessments.
        self.kyc = _r.Kyc(self._transport)
        #: Poll background jobs. ``kyc.assess()`` uses this for you.
        self.jobs = _r.Jobs(self._transport)
        #: Discover available rule sets.
        self.rule_sets = _r.RuleSets(self._transport)
        #: Discover individual rules and their testable fields.
        self.rules = _r.Rules(self._transport)
        #: Sanctions list screening.
        self.sanctions = _r.Sanctions(self._transport)
        #: Adverse media search.
        self.news = _r.News(self._transport)
        #: ICIJ Offshore Leaks screening.
        self.offshore_leaks = _r.OffshoreLeaks(self._transport)
        #: FCA Register lookups.
        self.fca = _r.Fca(self._transport)
        #: GLEIF LEI and parent-chain lookups.
        self.gleif = _r.Gleif(self._transport)
        #: Individual Insolvency Register screening.
        self.individual_insolvency = _r.IndividualInsolvency(self._transport)
        #: Charity Commission lookups.
        self.charity = _r.Charity(self._transport)
        #: HMRC VAT registration lookups.
        self.hmrc_vat = _r.HmrcVat(self._transport)
        #: FATF jurisdiction reference data.
        self.jurisdictions = _r.Jurisdictions(self._transport)
        #: Offshore jurisdiction reference data.
        self.offshore_jurisdictions = _r.OffshoreJurisdictions(self._transport)
        #: AI-written analysis. Professional plan.
        self.analysis = _r.Analysis(self._transport)
        #: Product documentation assistant.
        self.docs = _r.Docs(self._transport)

    @property
    def base_url(self) -> str:
        """The API root this client talks to."""
        return self._config.base_url

    @property
    def is_authenticated(self) -> bool:
        """Whether an API key was resolved. Anonymous clients hit lower limits."""
        return self._config.api_key is not None

    def health(self) -> JSON:
        """Liveness and dependency status. Unversioned, unauthenticated."""
        return self._transport.request("GET", "/health", versioned=False)

    def data_source_health(self) -> JSON:
        """Per-upstream availability: Companies House, FCA, GLEIF, sanctions, …"""
        return self._transport.request("GET", "/health/data-sources", versioned=False)

    def close(self) -> None:
        """Close the underlying connection pool, unless you supplied your own."""
        self._transport.close()

    def __enter__(self) -> KYCCentral:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        auth = "authenticated" if self.is_authenticated else "anonymous"
        return f"<KYCCentral base_url={self._config.base_url!r} {auth}>"


class AsyncKYCCentral:
    """Awaitable client for the KYC Central API.

    Mirrors :class:`KYCCentral` exactly — same namespaces, same method names,
    same arguments — with every call awaitable.

    The ``timeout`` argument is ignored when ``http_client`` is supplied;
    configure the timeout on that client. The per-call ``timeout`` on the AI
    endpoints still applies.

    Example:
        >>> import asyncio
        >>> from kyccentral import AsyncKYCCentral
        >>>
        >>> async def main():
        ...     async with AsyncKYCCentral(api_key="...") as client:
        ...         assessment = await client.kyc.assess("00445790")
        ...         print(assessment.risk_level)
        >>>
        >>> asyncio.run(main())
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._config = ClientConfig.resolve(
            api_key, base_url, timeout, max_retries, default_headers
        )
        self._transport = AsyncTransport(self._config, http_client)

        self.companies = _r.AsyncCompanies(self._transport)
        self.kyc = _r.AsyncKyc(self._transport)
        self.jobs = _r.AsyncJobs(self._transport)
        self.rule_sets = _r.AsyncRuleSets(self._transport)
        self.rules = _r.AsyncRules(self._transport)
        self.sanctions = _r.AsyncSanctions(self._transport)
        self.news = _r.AsyncNews(self._transport)
        self.offshore_leaks = _r.AsyncOffshoreLeaks(self._transport)
        self.fca = _r.AsyncFca(self._transport)
        self.gleif = _r.AsyncGleif(self._transport)
        self.individual_insolvency = _r.AsyncIndividualInsolvency(self._transport)
        self.charity = _r.AsyncCharity(self._transport)
        self.hmrc_vat = _r.AsyncHmrcVat(self._transport)
        self.jurisdictions = _r.AsyncJurisdictions(self._transport)
        self.offshore_jurisdictions = _r.AsyncOffshoreJurisdictions(self._transport)
        self.analysis = _r.AsyncAnalysis(self._transport)
        self.docs = _r.AsyncDocs(self._transport)

    @property
    def base_url(self) -> str:
        """The API root this client talks to."""
        return self._config.base_url

    @property
    def is_authenticated(self) -> bool:
        """Whether an API key was resolved."""
        return self._config.api_key is not None

    async def health(self) -> JSON:
        """Liveness and dependency status."""
        return await self._transport.request("GET", "/health", versioned=False)

    async def data_source_health(self) -> JSON:
        """Per-upstream availability."""
        return await self._transport.request("GET", "/health/data-sources", versioned=False)

    async def aclose(self) -> None:
        """Close the underlying connection pool, unless you supplied your own."""
        await self._transport.aclose()

    async def __aenter__(self) -> AsyncKYCCentral:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        auth = "authenticated" if self.is_authenticated else "anonymous"
        return f"<AsyncKYCCentral base_url={self._config.base_url!r} {auth}>"
