"""Assess one company and print a triage decision.

Run with:

    export KYCCENTRAL_API_KEY="your_key"
    python examples/assess_company.py 00445790
"""

from __future__ import annotations

import sys

from kyccentral import KYCCentral, KYCCentralError, RiskLevel


def main(company_number: str) -> int:
    with KYCCentral() as client:
        try:
            assessment = client.kyc.assess(company_number)
        except KYCCentralError as exc:
            print(f"Assessment failed: {exc}", file=sys.stderr)
            return 1

    print(f"{assessment.company_name} ({assessment.company_number})")
    print(f"Overall risk: {assessment.risk_level.value}")
    print(f"Registry data as of: {assessment.data_fetched_at}")
    print()

    if assessment.flags:
        print(f"{len(assessment.flags)} flag(s):")
        # Most severe first, so the blockers are at the top of the output.
        for flag in sorted(assessment.flags, key=lambda f: f.severity.rank, reverse=True):
            print(f"  [{flag.severity.value:<8}] {flag.code}: {flag.description}")
    else:
        print("No flags raised.")

    if assessment.is_partial:
        print()
        print("WARNING — this assessment is incomplete, so an absent flag is not a clear result.")
        if assessment.timed_out_services:
            print(f"  Timed out: {', '.join(assessment.timed_out_services)}")
        if assessment.unavailable_services:
            print(f"  Unavailable: {', '.join(assessment.unavailable_services)}")
        if assessment.failed_rules:
            print(f"  Rules that errored: {', '.join(assessment.failed_rules)}")
        if assessment.pending_extractions:
            print(f"  Still extracting: {', '.join(assessment.pending_extractions)}")

    print()
    if assessment.critical_flags:
        print("Decision: BLOCK — critical findings require escalation.")
        return 2
    if assessment.is_partial or assessment.risk_level is not RiskLevel.LOW:
        print("Decision: REFER for manual review.")
        return 0
    print("Decision: CLEAR.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <company_number>", file=sys.stderr)
        raise SystemExit(64)
    raise SystemExit(main(sys.argv[1]))
