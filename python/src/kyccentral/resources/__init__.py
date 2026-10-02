"""Resource namespaces exposed as attributes on the client.

Each namespace has a blocking class and an ``Async``-prefixed awaitable twin with
the same method names and signatures, so porting code between
:class:`~kyccentral.KYCCentral` and :class:`~kyccentral.AsyncKYCCentral` is a
matter of adding ``await``.
"""

from .analysis import Analysis, AsyncAnalysis, AsyncDocs, Docs
from .companies import AsyncCompanies, Companies
from .kyc import (
    AsyncJobs,
    AsyncKyc,
    AsyncRules,
    AsyncRuleSets,
    Jobs,
    Kyc,
    Rules,
    RuleSets,
)
from .registries import (
    AsyncCharity,
    AsyncHmrcVat,
    AsyncJurisdictions,
    AsyncOffshoreJurisdictions,
    Charity,
    HmrcVat,
    Jurisdictions,
    OffshoreJurisdictions,
)
from .reports import AsyncReports, Reports
from .screening import (
    AsyncGleif,
    AsyncIndividualInsolvency,
    AsyncNews,
    AsyncOffshoreLeaks,
    AsyncSanctions,
    Gleif,
    IndividualInsolvency,
    News,
    OffshoreLeaks,
    Sanctions,
)

__all__ = [
    "Analysis",
    "AsyncAnalysis",
    "AsyncCharity",
    "AsyncCompanies",
    "AsyncDocs",
    "AsyncGleif",
    "AsyncHmrcVat",
    "AsyncIndividualInsolvency",
    "AsyncJobs",
    "AsyncJurisdictions",
    "AsyncKyc",
    "AsyncNews",
    "AsyncOffshoreJurisdictions",
    "AsyncOffshoreLeaks",
    "AsyncReports",
    "AsyncRuleSets",
    "AsyncRules",
    "AsyncSanctions",
    "Charity",
    "Companies",
    "Docs",
    "Gleif",
    "HmrcVat",
    "IndividualInsolvency",
    "Jobs",
    "Jurisdictions",
    "Kyc",
    "News",
    "OffshoreJurisdictions",
    "OffshoreLeaks",
    "Reports",
    "RuleSets",
    "Rules",
    "Sanctions",
]
