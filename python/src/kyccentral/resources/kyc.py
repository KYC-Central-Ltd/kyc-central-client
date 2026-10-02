"""The risk assessment endpoint — the reason this API exists.

``assess()`` runs a rule set against one company and returns every risk flag it
raised, alongside the evidence each rule was evaluated against.

**Queued assessments.** A cold assessment fans out to a dozen upstream sources
and can take longer than a sensible HTTP timeout, so the API may accept the
request with ``202 Accepted`` and a job id instead of holding the connection
open. This client hides that: it polls the job to completion and returns the
finished :class:`~kyccentral.models.Assessment` either way. Use ``wait=False``
to get the raw envelope back and drive the polling yourself.
"""

from __future__ import annotations

import asyncio
import builtins
import time
from collections.abc import Sequence
from typing import Any

from .._transport import AsyncResource, SyncResource, _seg
from ..errors import JobFailedError, JobTimeoutError
from ..models import Assessment

__all__ = ["AsyncJobs", "AsyncKyc", "Jobs", "Kyc"]

JSON = dict[str, Any]

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 180.0

_QUEUED_STATUSES = frozenset({"queued", "running"})


def _assess_params(
    company_number: str | None,
    q: str | None,
    rule_set_id: str | None,
    rule_code: str | None,
    confirmed_media_urls: Sequence[str] | None,
    confirmed_leak_ids: Sequence[str] | None,
    confirmed_psc_shareholder_links: Sequence[str] | None,
) -> JSON:
    if not company_number and not q:
        raise ValueError("Provide either company_number or q.")
    if company_number and q:
        raise ValueError("Provide either company_number or q, not both.")
    return {
        "company_number": company_number,
        "q": q,
        "rule_set_id": rule_set_id,
        "rule_code": rule_code,
        "confirmed_media_url": list(confirmed_media_urls) if confirmed_media_urls else None,
        "confirmed_leak_id": list(confirmed_leak_ids) if confirmed_leak_ids else None,
        "confirmed_psc_shareholder_link": (
            list(confirmed_psc_shareholder_links) if confirmed_psc_shareholder_links else None
        ),
    }


def _check_poll_args(poll_interval: float, poll_timeout: float) -> None:
    """Reject non-positive polling parameters before any request is made.

    A zero or negative interval would poll the jobs endpoint in a tight loop.
    """
    if not poll_interval > 0:
        raise ValueError("poll_interval must be > 0")
    if not poll_timeout > 0:
        raise ValueError("poll_timeout must be > 0")


def _is_queued(payload: Any) -> bool:
    """True when the API returned a job envelope rather than an assessment."""
    return isinstance(payload, dict) and "job_id" in payload and "company_number" not in payload


def _job_outcome(state: JSON) -> JSON | None:
    """Return the finished result, or ``None`` while the job is still running.

    Raises :class:`JobFailedError` when the API reports the job as failed.
    """
    status = state.get("status")
    job_id = state.get("job_id")

    if status in _QUEUED_STATUSES:
        return None
    if status == "error":
        raise JobFailedError(str(state.get("error") or "The assessment job failed."), job_id=job_id)
    if status == "done":
        result = state.get("result")
        if isinstance(result, dict):
            return result
        raise JobFailedError(
            "The assessment finished but its result was no longer available — please re-run.",
            job_id=job_id,
        )
    raise JobFailedError(f"Unexpected job status {status!r}.", job_id=job_id)


class Jobs(SyncResource):
    """Poll background jobs started by the API.

    You rarely need this directly: ``client.kyc.assess()`` polls for you.
    """

    def get(self, job_id: str) -> JSON:
        """Current state of a job: ``{"job_id", "status", "result"?, "error"?}``.

        ``status`` is one of ``queued``, ``running``, ``done`` or ``error``.
        """
        return self._get(f"/jobs/{_seg(job_id, 'job_id')}")


class AsyncJobs(AsyncResource):
    """Awaitable mirror of :class:`Jobs`."""

    async def get(self, job_id: str) -> JSON:
        """Current state of a job."""
        return await self._get(f"/jobs/{_seg(job_id, 'job_id')}")


class Kyc(SyncResource):
    """Run risk assessments. **Requires an API key** on every plan.

    Free-plan keys are capped at a fixed number of assessments per calendar
    month; exceeding it raises
    :class:`~kyccentral.errors.RateLimitError`. Cached results and failed runs do
    not consume quota.
    """

    def assess(
        self,
        company_number: str | None = None,
        *,
        q: str | None = None,
        rule_set_id: str | None = None,
        rule_code: str | None = None,
        confirmed_media_urls: Sequence[str] | None = None,
        confirmed_leak_ids: Sequence[str] | None = None,
        confirmed_psc_shareholder_links: Sequence[str] | None = None,
        wait: bool = True,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> Assessment | JSON:
        """Assess one company against a rule set.

        Args:
            company_number: Companies House number, e.g. ``"00445790"``. Mutually
                exclusive with ``q``.
            q: Company name to search — the top search result is assessed. Use
                this only when you do not have a number; prefer ``company_number``
                so you always know which entity you screened.
            rule_set_id: Rule set slug. Defaults to the API's ``"default"`` set.
                Call ``client.rule_sets.list()`` for the available sets.
            rule_code: Run a single rule instead of a whole set, e.g.
                ``"ACCOUNTS_OVERDUE"``. Overrides ``rule_set_id``.
            confirmed_media_urls: Adverse-media article URLs an analyst has
                already confirmed as genuine hits. Unconfirmed matches only ever
                raise a low-severity ``ADVERSE_MEDIA_UNCONFIRMED`` flag; passing
                a URL here promotes that article to its full severity.
            confirmed_leak_ids: ICIJ Offshore Leaks match ids an analyst has
                confirmed, promoting ``OFFSHORE_LEAKS_UNCONFIRMED`` in the same way.
            confirmed_psc_shareholder_links: Analyst-confirmed identity links
                between a PSC and a shareholder, each formatted
                ``"<psc name>||<shareholder name>"``.
            wait: When True (the default), poll a queued assessment to completion
                and return the finished result. When False, return the raw
                ``{"job_id": ..., "status": "queued"}`` envelope immediately if
                the API queued the work.
            poll_interval: Seconds between polls of a queued job.
            poll_timeout: Give up waiting after this many seconds and raise
                :class:`~kyccentral.errors.JobTimeoutError`.

        Returns:
            An :class:`~kyccentral.models.Assessment`. With ``wait=False`` a
            queued request returns the job envelope as a plain ``dict`` instead.

        Raises:
            ValueError: Neither or both of ``company_number`` and ``q`` given, or
                ``poll_interval`` / ``poll_timeout`` is not greater than zero.
            ~kyccentral.errors.AuthenticationError: No API key configured.
            ~kyccentral.errors.NotFoundError: No such company, rule set or rule.
            ~kyccentral.errors.RateLimitError: Rate limit or monthly free quota hit.
            ~kyccentral.errors.JobTimeoutError: Queued assessment outran ``poll_timeout``.
        """
        _check_poll_args(poll_interval, poll_timeout)
        payload = self._get(
            "/kyc/assess",
            params=_assess_params(
                company_number,
                q,
                rule_set_id,
                rule_code,
                confirmed_media_urls,
                confirmed_leak_ids,
                confirmed_psc_shareholder_links,
            ),
        )

        if not _is_queued(payload):
            return Assessment.from_dict(payload)
        if not wait:
            return payload

        return Assessment.from_dict(
            self._await_job(str(payload["job_id"]), poll_interval, poll_timeout)
        )

    def _await_job(self, job_id: str, poll_interval: float, poll_timeout: float) -> JSON:
        deadline = time.monotonic() + poll_timeout
        while True:
            state = self._get(f"/jobs/{_seg(job_id, 'job_id')}")
            result = _job_outcome(state)
            if result is not None:
                return result
            if time.monotonic() + poll_interval > deadline:
                raise JobTimeoutError(
                    f"Assessment job {job_id} did not finish within {poll_timeout:g}s. "
                    "It may still complete — re-running the same request will return "
                    "the cached result once it does.",
                    job_id=job_id,
                )
            time.sleep(poll_interval)


class AsyncKyc(AsyncResource):
    """Awaitable mirror of :class:`Kyc`. See there for full documentation."""

    async def assess(
        self,
        company_number: str | None = None,
        *,
        q: str | None = None,
        rule_set_id: str | None = None,
        rule_code: str | None = None,
        confirmed_media_urls: Sequence[str] | None = None,
        confirmed_leak_ids: Sequence[str] | None = None,
        confirmed_psc_shareholder_links: Sequence[str] | None = None,
        wait: bool = True,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> Assessment | JSON:
        """Assess one company against a rule set."""
        _check_poll_args(poll_interval, poll_timeout)
        payload = await self._get(
            "/kyc/assess",
            params=_assess_params(
                company_number,
                q,
                rule_set_id,
                rule_code,
                confirmed_media_urls,
                confirmed_leak_ids,
                confirmed_psc_shareholder_links,
            ),
        )

        if not _is_queued(payload):
            return Assessment.from_dict(payload)
        if not wait:
            return payload

        return Assessment.from_dict(
            await self._await_job(str(payload["job_id"]), poll_interval, poll_timeout)
        )

    async def _await_job(self, job_id: str, poll_interval: float, poll_timeout: float) -> JSON:
        loop_deadline = time.monotonic() + poll_timeout
        while True:
            state = await self._get(f"/jobs/{_seg(job_id, 'job_id')}")
            result = _job_outcome(state)
            if result is not None:
                return result
            if time.monotonic() + poll_interval > loop_deadline:
                raise JobTimeoutError(
                    f"Assessment job {job_id} did not finish within {poll_timeout:g}s. "
                    "It may still complete — re-running the same request will return "
                    "the cached result once it does.",
                    job_id=job_id,
                )
            await asyncio.sleep(poll_interval)


class RuleSets(SyncResource):
    """Discover the rule sets available to your key."""

    def list(self) -> builtins.list[JSON]:
        """Every rule set you can run: built-ins plus your workspace sets."""
        return self._get("/rule-sets")


class AsyncRuleSets(AsyncResource):
    """Awaitable mirror of :class:`RuleSets`."""

    async def list(self) -> builtins.list[JSON]:
        """Every rule set you can run."""
        return await self._get("/rule-sets")


class Rules(SyncResource):
    """Discover individual rules and the company fields they can test."""

    def list(self) -> builtins.list[JSON]:
        """Every rule, with its code, severity and rationale."""
        return self._get("/rules")

    def fields(self) -> Any:
        """Company data fields exposed to configurable rule conditions."""
        return self._get("/rules/fields")


class AsyncRules(AsyncResource):
    """Awaitable mirror of :class:`Rules`."""

    async def list(self) -> builtins.list[JSON]:
        """Every rule, with its code, severity and rationale."""
        return await self._get("/rules")

    async def fields(self) -> Any:
        """Company data fields exposed to configurable rule conditions."""
        return await self._get("/rules/fields")


__all__ += ["AsyncRuleSets", "AsyncRules", "RuleSets", "Rules"]
