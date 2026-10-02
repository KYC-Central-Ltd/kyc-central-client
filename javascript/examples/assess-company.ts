/**
 * Assess one company and print a triage decision.
 *
 * Run with:
 *
 *     export KYCCENTRAL_API_KEY="your_key"
 *     npx tsx examples/assess-company.ts 00445790
 */

import {
  KYCCentral,
  KYCCentralError,
  RISK_LEVEL_RANK,
  isPartial,
  type RiskFlag,
} from '../src/index.js';

async function main(companyNumber: string): Promise<number> {
  const client = new KYCCentral();

  let assessment;
  try {
    assessment = await client.kyc.assess(companyNumber);
  } catch (error) {
    if (error instanceof KYCCentralError) {
      console.error(`Assessment failed: ${error.message}`);
      return 1;
    }
    throw error;
  }

  console.log(`${assessment.companyName} (${assessment.companyNumber})`);
  console.log(`Overall risk: ${assessment.riskLevel}`);
  console.log(`Registry data as of: ${assessment.dataFetchedAt}`);
  console.log();

  if (assessment.flags.length > 0) {
    console.log(`${assessment.flags.length} flag(s):`);
    // Most severe first, so the blockers are at the top of the output.
    const bySeverity = [...assessment.flags].sort(
      (a: RiskFlag, b: RiskFlag) => RISK_LEVEL_RANK[b.severity] - RISK_LEVEL_RANK[a.severity],
    );
    for (const flag of bySeverity) {
      console.log(`  [${flag.severity.padEnd(8)}] ${flag.code}: ${flag.description}`);
    }
  } else {
    console.log('No flags raised.');
  }

  if (isPartial(assessment)) {
    console.log();
    console.log(
      'WARNING — this assessment is incomplete, so an absent flag is not a clear result.',
    );
    if (assessment.timedOutServices.length) {
      console.log(`  Timed out: ${assessment.timedOutServices.join(', ')}`);
    }
    if (assessment.unavailableServices.length) {
      console.log(`  Unavailable: ${assessment.unavailableServices.join(', ')}`);
    }
    if (assessment.failedRules.length) {
      console.log(`  Rules that errored: ${assessment.failedRules.join(', ')}`);
    }
    if (assessment.pendingExtractions.length) {
      console.log(`  Still extracting: ${assessment.pendingExtractions.join(', ')}`);
    }
  }

  console.log();
  const critical = assessment.flags.filter((flag) => flag.severity === 'critical');
  if (critical.length > 0) {
    console.log('Decision: BLOCK — critical findings require escalation.');
    return 2;
  }
  if (isPartial(assessment) || assessment.riskLevel !== 'low') {
    console.log('Decision: REFER for manual review.');
    return 0;
  }
  console.log('Decision: CLEAR.');
  return 0;
}

const companyNumber = process.argv[2];
if (!companyNumber) {
  console.error('usage: assess-company.ts <company_number>');
  process.exit(64);
}

main(companyNumber).then(
  (code) => process.exit(code),
  (error) => {
    console.error(error);
    process.exit(1);
  },
);
