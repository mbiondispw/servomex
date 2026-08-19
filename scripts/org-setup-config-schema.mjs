/**
 * Shared schema + validator for org-setup.config.json (W-23043729).
 *
 * Authored ONCE, used at TWO moments:
 *   (a) build / CI time — `scripts/validate-org-setup-config.mjs` validates every
 *       org-setup.config.json this repo ships, failing the build on any violation.
 *   (b) setup runtime — `org-setup.mjs` calls `validateConfig` once in main(),
 *       before any step runs, to catch the developer's local post-scaffold edits.
 *
 * `validateConfig` is pure: it parses + validates and RETURNS a result. Each call
 * site owns its own print/exit, so the build gate can report every bad file and
 * the runtime can exit immediately — and the validator stays unit-testable.
 *
 * The zod schema uses `.strict()` at every level so unknown keys (e.g. the
 * `permsetAssignment` singular typo) are rejected rather than silently ignored.
 */

import { z } from 'zod';

/** Closed set of assignee values — no arbitrary usernames. */
const Assignee = z.enum(['currentUser', 'guestUser', 'skip']);

// No siteName: for guestUser the site is derived from the single
// networks/<siteName>.network-meta.xml the app ships (see spec §5.2).
const Assignment = z
  .object({
    assignee: Assignee,
  })
  .strict();

export const ConfigSchema = z
  .object({
    permsetAssignments: z
      .object({
        // guestUser is valid here — siteName is derived, not per-assignment.
        defaultAssignee: Assignee.default('skip'),
        assignments: z.record(z.string(), Assignment).default({}),
      })
      .strict()
      .optional(),
    role: z
      .object({
        assignee: z.literal('currentUser'), // only value the role code honors
        roleName: z.string().min(1),
      })
      .strict()
      .optional(),
    selfRegistration: z
      .object({
        // No siteName: the site is derived from the single
        // networks/<siteName>.network-meta.xml the app ships (see spec §5.2),
        // exactly like the guestUser permset path.
        selfRegProfile: z.string().min(1),
        accountName: z.string().min(1),
      })
      .strict()
      .optional(),
  })
  .strict();

/**
 * Render a single zod issue as a "path: message" line. Empty path (a root-level
 * problem) renders as "<root>: message".
 */
function formatIssue(issue) {
  const path = issue.path.length > 0 ? issue.path.join('.') : '<root>';
  return `${path}: ${issue.message}`;
}

/**
 * Parse + validate a raw org-setup.config.json string.
 *
 * @param {string} rawText  raw file contents (not yet JSON-parsed)
 * @param {string} [configPath]  path used only for error messages
 * @returns {{ ok: true, data: object } | { ok: false, errors: string[] }}
 *   On success, `data` is the parsed + defaulted config. On failure, `errors`
 *   is a non-empty list of human-readable messages (JSON parse error or zod
 *   issues). The caller decides whether to print/exit.
 */
export function validateConfig(rawText, configPath) {
  const where = configPath ? ` (${configPath})` : '';

  let parsed;
  try {
    parsed = JSON.parse(rawText);
  } catch (err) {
    return { ok: false, errors: [`malformed JSON${where}: ${err.message}`] };
  }

  const result = ConfigSchema.safeParse(parsed);
  if (!result.success) {
    return { ok: false, errors: result.error.issues.map(formatIssue) };
  }

  return { ok: true, data: result.data };
}
