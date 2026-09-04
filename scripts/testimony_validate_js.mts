/* Run the browser validator from the command line, so the Python reference and
 * the TypeScript port can be compared over the same records.
 *
 *   node --experimental-strip-types scripts/testimony_validate_js.mts record.jsonl
 *
 * Emits the same facts the Python validator's --json does, in the same shape,
 * so a test can diff them without either side knowing about the comparison.
 *
 * Copyright 2026 Michael Brandon Clifford. MIT licensed. */
import { readFileSync } from 'node:fs';
import { validate } from '../web/lib/testimony.ts';

const report = validate(readFileSync(process.argv[2], 'utf8'));
console.log(
  JSON.stringify({
    spec: report.spec,
    scope: report.scope,
    level: report.level,
    levels_met: report.levelsMet,
    checks: report.checks.map((c) => [c.level, c.check, c.ok]),
  }),
);
