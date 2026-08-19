#!/usr/bin/env node
/**
 * One-command setup: login, deploy, optional permset/data, GraphQL schema/codegen, UI bundle build.
 * Use this script to make setup easier for each app generated from this template.
 *
 * Usage:
 *   node scripts/org-setup.mjs --target-org <alias>           # interactive step picker (all selected)
 *   node scripts/org-setup.mjs --target-org <alias> --yes     # skip picker, run all steps
 *   node scripts/org-setup.mjs --target-org afv5 --skip-login
 *   node scripts/org-setup.mjs --target-org afv5 --skip-data --skip-ui-bundle-build
 *   node scripts/org-setup.mjs --target-org myorg --ui-bundle-name my-app
 *
 * Steps (in order):
 *   1. login     — sf org login web only if org not already connected (skip with --skip-login)
 *   2. uiBundle  — (all UI bundles) npm install && npm run build so dist exists for deploy (skip with --skip-ui-bundle-build)
 *   3. deploy    — sf project deploy start --target-org <alias> (requires dist for entity deployment)
 *   4. permset   — assign permsets per org-setup.config.json (skip with --skip-permset; override via --permset-name)
 *   5. data      — prepare unique fields + sf data import tree (skipped if no data dir/plan)
 *   6. graphql   — (in UI bundle) npm run graphql:schema then npm run graphql:codegen
 *   7. dev       — (in UI bundle) npm run dev — launch dev server (skip with --skip-dev)
 *
 * Permset assignment config (scripts/org-setup.config.json):
 *   {
 *     "permsetAssignments": {
 *       "defaultAssignee": "skip",
 *       "assignments": {
 *         "My_Permset": { "assignee": "currentUser" },
 *         "Guest_Permset": { "assignee": "guestUser" },
 *         "Internal_Only": { "assignee": "skip" }
 *       }
 *     }
 *   }
 *   Assignee values: "currentUser", "guestUser", or "skip". For "guestUser" the
 *   site is derived from the single networks/<siteName>.network-meta.xml the app
 *   ships — it is not restated per assignment.
 *   Unlisted permsets resolve to "defaultAssignee" (default "skip").
 */

import { spawnSync, spawn as nodeSpawn } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readdirSync, existsSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs';

import { validateConfig } from './org-setup-config-schema.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

/**
 * Thrown by step runners (run/runAsync) when a subprocess fails. The per-step
 * orchestration in main() catches it, records the failure in the result ledger,
 * and either aborts (fail-fast steps) or continues (skippable steps).
 */
class StepError extends Error {}

/**
 * npm strips .gitignore from published packages — generate them on first run.
 * Templates are stored in scripts/gitignore-templates.json (generated at build
 * time from the actual .gitignore files) so the content lives in one place.
 * The JSON may not exist in git-cloned distributions where .gitignore is
 * already present, so loading is best-effort.
 */
function loadGitignoreTemplates() {
  const templatesPath = resolve(__dirname, 'gitignore-templates.json');
  if (!existsSync(templatesPath)) return null;
  try {
    return JSON.parse(readFileSync(templatesPath, 'utf8'));
  } catch {
    return null;
  }
}

function ensureGitignore(dir, content) {
  if (!content) return;
  const gitignorePath = resolve(dir, '.gitignore');
  if (!existsSync(gitignorePath)) {
    writeFileSync(gitignorePath, content, 'utf8');
    console.log(`Created .gitignore in ${dir}`);
  }
}

function resolveSfdxSource() {
  const sfdxPath = resolve(ROOT, 'sfdx-project.json');
  if (!existsSync(sfdxPath)) {
    console.error('Error: sfdx-project.json not found at project root.');
    process.exit(1);
  }
  const sfdxProject = JSON.parse(readFileSync(sfdxPath, 'utf8'));
  const pkgDir = sfdxProject?.packageDirectories?.[0]?.path;
  if (!pkgDir) {
    console.error('Error: No packageDirectories[].path found in sfdx-project.json.');
    process.exit(1);
  }
  return resolve(ROOT, pkgDir, 'main', 'default');
}

const SFDX_SOURCE = resolveSfdxSource();
const UIBUNDLES_DIR = resolve(SFDX_SOURCE, 'uiBundles');
const DATA_DIR = resolve(SFDX_SOURCE, 'data');
const DATA_PLAN = resolve(SFDX_SOURCE, 'data/data-plan.json');

function parseArgs() {
  const args = process.argv.slice(2);
  let targetOrg = null;
  let uiBundleName = null;
  /** If non-empty, only these names are assigned; otherwise all discovered from the project. */
  const permsetNamesExplicit = [];
  let yes = false;
  const flags = {
    skipLogin: false,
    skipDeploy: false,
    skipPermset: false,
    skipRole: false,
    skipData: false,
    skipGraphql: false,
    skipUIBundleBuild: false,
    skipSelfReg: false,
    skipDev: false,
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--target-org' && args[i + 1]) {
      targetOrg = args[++i];
    } else if (args[i] === '--ui-bundle-name' && args[i + 1]) {
      uiBundleName = args[++i];
    } else if (args[i] === '--permset-name' && args[i + 1]) {
      permsetNamesExplicit.push(args[++i]);
    } else if (args[i] === '--skip-login') flags.skipLogin = true;
    else if (args[i] === '--skip-deploy') flags.skipDeploy = true;
    else if (args[i] === '--skip-permset') flags.skipPermset = true;
    else if (args[i] === '--skip-role') flags.skipRole = true;
    else if (args[i] === '--skip-data') flags.skipData = true;
    else if (args[i] === '--skip-self-reg') flags.skipSelfReg = true;
    else if (args[i] === '--skip-graphql') flags.skipGraphql = true;
    else if (args[i] === '--skip-ui-bundle-build') flags.skipUIBundleBuild = true;
    else if (args[i] === '--skip-dev') flags.skipDev = true;
    else if (args[i] === '--yes' || args[i] === '-y') yes = true;
    else if (args[i] === '--help' || args[i] === '-h') {
      console.log(`
Setup CLI — one-command setup for apps in this project

Usage:
  node scripts/org-setup.mjs --target-org <alias> [options]

Required:
  --target-org <alias>   Target Salesforce org alias (e.g. myorg)

Options:
  --ui-bundle-name <name> UI bundle folder name under uiBundles/ (default: auto-detect)
  --permset-name <name>  Assign only this permission set (repeatable). Default: all sets under permissionsets/
  --skip-login           Skip login step (login is auto-skipped if org is already connected)
  --skip-deploy          Do not deploy metadata
  --skip-permset         Do not assign permission set
  --skip-data            Do not prepare data or run data import
  --skip-graphql         Do not fetch schema or run GraphQL codegen
  --skip-ui-bundle-build Do not npm install / build the UI bundle
  --skip-dev             Do not launch the dev server at the end
  -y, --yes              Skip interactive step picker; run all enabled steps immediately
  -h, --help             Show this help

Permset config (scripts/org-setup.config.json):
  Control per-permset assignment via a config file. Example:
    {
      "permsetAssignments": {
        "defaultAssignee": "skip",
        "assignments": {
          "My_Permset": { "assignee": "currentUser" },
          "Guest_Permset": { "assignee": "guestUser" },
          "Internal_Only": { "assignee": "skip" }
        }
      }
    }
  Assignee values: "currentUser", "guestUser", or "skip". For "guestUser" the site
  is derived from the single networks/<siteName>.network-meta.xml the app ships.
  Unlisted permsets resolve to "defaultAssignee" (default "skip").
`);
      process.exit(0);
    }
  }
  if (!targetOrg) {
    console.error('Error: --target-org <alias> is required.');
    process.exit(1);
  }
  return { targetOrg, uiBundleName, permsetNamesExplicit, yes, ...flags };
}

function discoverAllUIBundleDirs(uiBundleName) {
  if (!existsSync(UIBUNDLES_DIR)) {
    console.error(`Error: uiBundles directory not found: ${UIBUNDLES_DIR}`);
    process.exit(1);
  }
  const entries = readdirSync(UIBUNDLES_DIR, { withFileTypes: true });
  const dirs = entries.filter((e) => e.isDirectory() && !e.name.startsWith('.'));
  if (dirs.length === 0) {
    console.error(`Error: No UI bundle folder found under ${UIBUNDLES_DIR}`);
    process.exit(1);
  }
  if (uiBundleName) {
    const requested = dirs.find((d) => d.name === uiBundleName);
    if (!requested) {
      console.error(`Error: UI bundle directory not found: ${uiBundleName}`);
      process.exit(1);
    }
    return [resolve(UIBUNDLES_DIR, requested.name)];
  }
  return dirs.map((d) => resolve(UIBUNDLES_DIR, d.name));
}

function discoverUIBundleDir(uiBundleName) {
  const all = discoverAllUIBundleDirs(uiBundleName);
  if (all.length > 1 && !uiBundleName) {
    console.log(`Multiple UI bundles found; using first: ${all[0].split(/[/\\]/).pop()}`);
  }
  return all[0];
}

/** API names from permissionsets/*.permissionset-meta.xml in the first package directory. */
function discoverPermissionSetNames() {
  const dir = resolve(SFDX_SOURCE, 'permissionsets');
  if (!existsSync(dir)) return [];
  const names = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const m = entry.name.match(/^(.+)\.permissionset-meta\.xml$/);
    if (m) names.push(m[1]);
  }
  return names.sort();
}

const CONFIG_PATH = resolve(__dirname, 'org-setup.config.json');

/**
 * Read + validate org-setup.config.json ONCE, against the shared zod schema
 * (the same `validateConfig` the build/CI gate uses). Exits non-zero with the
 * precise zod issues if the config is invalid — before any step runs.
 *
 * Returns the validated config object (zod defaults applied), or an empty
 * object when the file is absent (every section is optional).
 *
 * This is the single source of truth: loadPermsetConfig / loadRoleConfig /
 * loadSelfRegConfig all read from the object it returns, so they no longer
 * parse or defensively swallow errors.
 */
function loadValidatedConfig() {
  if (!existsSync(CONFIG_PATH)) return {};
  const result = validateConfig(readFileSync(CONFIG_PATH, 'utf8'), CONFIG_PATH);
  if (!result.ok) {
    console.error('Invalid org-setup.config.json:');
    for (const err of result.errors) console.error(`  - ${err}`);
    process.exit(1);
  }
  return result.data;
}

/**
 * Derive the site name from the single networks/<siteName>.network-meta.xml the
 * app ships. An app ships exactly one site, so the site name is derivable from
 * deployed metadata rather than restated per-assignment (spec §5.2). Returns
 * null when there is no networks dir or no .network-meta.xml file.
 */
function deriveSiteName() {
  const networksDir = resolve(SFDX_SOURCE, 'networks');
  if (!existsSync(networksDir)) return null;
  const files = readdirSync(networksDir)
    .filter((f) => f.endsWith('.network-meta.xml'))
    .sort();
  if (files.length === 0) return null;
  // An app ships exactly one site; if a developer added a second, derivation is
  // ambiguous — fail loudly rather than silently bind to an arbitrary site.
  if (files.length > 1) {
    throw new StepError(
      `cannot derive guest site: multiple network metadata files found in ${networksDir} (${files.join(', ')}); guestUser assignment requires exactly one`,
    );
  }
  return files[0].replace(/\.network-meta\.xml$/, '');
}

/**
 * Permset assignment configuration, read from the already-validated config.
 *
 * Config shape:
 *   {
 *     "permsetAssignments": {
 *       "defaultAssignee": "skip",
 *       "assignments": {
 *         "My_Permset":       { "assignee": "currentUser" },
 *         "My_Guest_Permset": { "assignee": "guestUser" },
 *         "Internal_Only":    { "assignee": "skip" }
 *       }
 *     }
 *   }
 *
 * Assignee values:
 *   "currentUser" — assign to the user running the script
 *   "skip"        — do not assign this permset
 *   "guestUser"   — resolve the site guest user automatically (site derived from
 *                   the single networks/<siteName>.network-meta.xml the app ships)
 *
 * Unlisted permsets resolve to `defaultAssignee` (default "skip").
 *
 * Returns { defaultAssignee: string, assignments: Record<string, { assignee: string }> }
 */
function loadPermsetConfig(config) {
  const section = config.permsetAssignments;
  if (!section) return { defaultAssignee: 'skip', assignments: {} };
  return {
    defaultAssignee: section.defaultAssignee,
    assignments: section.assignments,
  };
}

/** Resolve the effective assignment config for a given permset name. */
function resolveAssignment(permsetName, permsetConfig) {
  const override = permsetConfig.assignments[permsetName];
  if (!override) return { assignee: permsetConfig.defaultAssignee };
  return { assignee: override.assignee };
}

/**
 * Role assignment config, read from the already-validated config.
 *
 * Config shape:
 *   { "role": { "assignee": "currentUser", "roleName": "Admin" } }
 *
 * Returns null if no "role" section exists in config (the step is hidden).
 */
function loadRoleConfig(config) {
  const section = config.role;
  if (!section) return null;
  return {
    assignee: section.assignee,
    roleName: section.roleName,
  };
}

/**
 * Self-registration config, read from the already-validated config. The site is
 * NOT stored here — it is derived from the single
 * networks/<siteName>.network-meta.xml the app ships (spec §5.2), exactly like
 * the guestUser permset path. deriveSiteName() is called lazily inside the
 * selfReg step body so its "multiple network files" StepError is recorded in
 * the ledger rather than escaping config load.
 *
 * Config shape:
 *   {
 *     "selfRegistration": {
 *       "selfRegProfile": "myapp Profile",
 *       "accountName": "My Self-Reg Account"
 *     }
 *   }
 *
 * Returns null if no "selfRegistration" section exists in config (the step is hidden).
 */
function loadSelfRegConfig(config) {
  const section = config.selfRegistration;
  if (!section) return null;
  return {
    selfRegProfile: section.selfRegProfile,
    accountName: section.accountName,
  };
}

/**
 * Ensure the self-registration profile is listed in networkMemberGroups.
 * This must happen BEFORE the initial deploy so that the profile is a recognised
 * site member when subsequent steps (selfRegProfile, selfRegistration=true) are deployed.
 */
function ensureNetworkMemberProfile(selfRegConfig, siteName) {
  const { selfRegProfile } = selfRegConfig;
  if (!siteName || !selfRegProfile) return;

  const networkXmlPath = resolve(SFDX_SOURCE, 'networks', `${siteName}.network-meta.xml`);
  if (!existsSync(networkXmlPath)) {
    console.log(`  Network metadata not found: ${networkXmlPath}; skipping member group update.`);
    return;
  }
  const xml = readFileSync(networkXmlPath, 'utf8');

  // Check if profile is already in networkMemberGroups
  const profileEscaped = selfRegProfile.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const profileRegex = new RegExp(`<profile>\\s*${profileEscaped}\\s*</profile>`);
  if (profileRegex.test(xml)) {
    console.log(`  Profile "${selfRegProfile}" already in networkMemberGroups; no update needed.`);
    return;
  }

  // Add the profile to networkMemberGroups
  const updatedXml = xml.replace(
    /(<networkMemberGroups>)/,
    `$1\n        <profile>${selfRegProfile}</profile>`
  );
  writeFileSync(networkXmlPath, updatedXml);
  console.log(`  Added profile "${selfRegProfile}" to networkMemberGroups in ${siteName}.network-meta.xml`);
}

/**
 * Enable self-registration for an Experience Cloud network.
 *
 * 1. Modify the network metadata XML to set selfRegistration=true and add selfRegProfile.
 * 2. Re-deploy the modified network metadata.
 * 3. Create an Account record (idempotent).
 * 4. Create a NetworkSelfRegistration record linking the Account to the Network (idempotent).
 */
function enableSelfRegistration(selfRegConfig, siteName, targetOrg) {
  const { selfRegProfile, accountName } = selfRegConfig;

  // 1. Modify network metadata XML
  const networkXmlPath = resolve(SFDX_SOURCE, 'networks', `${siteName}.network-meta.xml`);
  if (!existsSync(networkXmlPath)) {
    throw new StepError(`network metadata not found: ${networkXmlPath}`);
  }
  const xml = readFileSync(networkXmlPath, 'utf8');

  // Skip network modification and deploy if self-registration is already configured
  const alreadyEnabled = /<selfRegistration>true<\/selfRegistration>/.test(xml);
  const alreadyHasProfile = /<selfRegProfile>/.test(xml);
  if (alreadyEnabled || alreadyHasProfile) {
    console.log(`  Network "${siteName}" already has self-registration configured; skipping metadata update and deploy.`);
  } else {
    // Set selfRegistration to true and add selfRegProfile
    let updatedXml = xml.replace(
      /<selfRegistration>false<\/selfRegistration>/,
      '<selfRegistration>true</selfRegistration>'
    );
    updatedXml = updatedXml.replace(
      /(\s*)(<selfRegistration>)/,
      `$1<selfRegProfile>${selfRegProfile}</selfRegProfile>\n$1$2`
    );

    writeFileSync(networkXmlPath, updatedXml);
    console.log(`  Updated ${siteName}.network-meta.xml: selfRegistration=true, selfRegProfile=${selfRegProfile}`);

    // Re-deploy only the network file
    const deployResult = spawnSync('sf', [
      'project', 'deploy', 'start',
      '--target-org', targetOrg,
      '--source-dir', networkXmlPath,
    ], { cwd: ROOT, stdio: 'inherit', shell: true, timeout: 120000 });
    if (deployResult.status !== 0) {
      throw new StepError(`failed to deploy updated network metadata (exit ${deployResult.status ?? 1})`);
    }
  }

  // 3. Create Account (idempotent)
  const acctQuery = `SELECT Id FROM Account WHERE Name = '${accountName.replace(/'/g, "\\'")}' LIMIT 1`;
  const acctQueryResult = spawnSync('sf', [
    'data', 'query',
    '--query', acctQuery,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  let accountId = null;
  if (acctQueryResult.status === 0) {
    try {
      const json = JSON.parse(acctQueryResult.stdout);
      accountId = json.result?.records?.[0]?.Id || null;
    } catch { /* proceed to create */ }
  }
  if (accountId) {
    console.log(`  Account "${accountName}" already exists (${accountId}); skipping creation.`);
  } else {
    const createResult = spawnSync('sf', [
      'data', 'create', 'record',
      '--sobject', 'Account',
      '--values', `Name='${accountName}'`,
      '--target-org', targetOrg,
      '--json',
    ], { cwd: ROOT, encoding: 'utf8' });
    if (createResult.status !== 0) {
      if (createResult.stderr) console.error(createResult.stderr);
      throw new StepError(`failed to create Account "${accountName}"`);
    }
    try {
      const json = JSON.parse(createResult.stdout);
      accountId = json.result?.id;
      console.log(`  Created Account "${accountName}" (${accountId}).`);
    } catch {
      throw new StepError('failed to parse Account creation result');
    }
  }

  // 4. Query Network Id
  const netQuery = `SELECT Id FROM Network WHERE Name = '${siteName}'`;
  const netResult = spawnSync('sf', [
    'data', 'query',
    '--query', netQuery,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  let networkId = null;
  if (netResult.status === 0) {
    try {
      const json = JSON.parse(netResult.stdout);
      networkId = json.result?.records?.[0]?.Id || null;
    } catch { /* fall through */ }
  }
  if (!networkId) {
    throw new StepError(`could not find Network "${siteName}" in org`);
  }
  console.log(`  Found Network "${siteName}" (${networkId}).`);

  // 5. Create NetworkSelfRegistration (idempotent)
  const nsrQuery = `SELECT Id FROM NetworkSelfRegistration WHERE NetworkId = '${networkId}'`;
  const nsrResult = spawnSync('sf', [
    'data', 'query',
    '--query', nsrQuery,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  let nsrExists = false;
  if (nsrResult.status === 0) {
    try {
      const json = JSON.parse(nsrResult.stdout);
      nsrExists = (json.result?.records?.length || 0) > 0;
    } catch { /* proceed to create */ }
  }
  if (nsrExists) {
    console.log('  NetworkSelfRegistration record already exists; skipping.');
  } else {
    const tmpApex = resolve(ROOT, '.tmp-setup-selfreg.apex');
    const apex = [
      `Account acct = [SELECT Id FROM Account WHERE Id = '${accountId}' LIMIT 1];`,
      `NetworkSelfRegistration nsr = new NetworkSelfRegistration();`,
      `nsr.AccountId = acct.Id;`,
      `nsr.NetworkId = '${networkId}';`,
      `insert nsr;`,
      `System.debug('NSR_CREATED:' + nsr.Id);`,
    ].join('\n');
    writeFileSync(tmpApex, apex);
    const apexResult = spawnSync('sf', [
      'apex', 'run', '--target-org', targetOrg, '--file', tmpApex,
    ], { cwd: ROOT, stdio: 'pipe', shell: true, timeout: 60000 });
    const apexOut = apexResult.stdout?.toString() || '';
    if (existsSync(tmpApex)) unlinkSync(tmpApex);
    if (apexResult.status !== 0 && !apexOut.includes('Compiled successfully')) {
      process.stderr.write(apexResult.stderr?.toString() || apexOut);
      throw new StepError('failed to create NetworkSelfRegistration record');
    }
    const nsrMatch = apexOut.match(/NSR_CREATED:(\w+)/);
    if (nsrMatch) {
      console.log(`  Created NetworkSelfRegistration (${nsrMatch[1]}).`);
    } else {
      console.log('  NetworkSelfRegistration creation executed.');
    }
  }
}

/**
 * Assign a role to the current user so that Experience Cloud self-registration
 * works correctly.
 */
function assignRoleToCurrentUser(roleName, targetOrg) {
  const roleQuery = `SELECT Id FROM UserRole WHERE Name = '${roleName}'`;
  const roleResult = spawnSync('sf', [
    'data', 'query',
    '--query', roleQuery,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  if (roleResult.status !== 0) {
    if (roleResult.stderr) console.error(roleResult.stderr);
    throw new StepError(`failed to query role "${roleName}" in org`);
  }
  let roleId;
  try {
    const json = JSON.parse(roleResult.stdout);
    const records = json.result?.records;
    if (!records || records.length === 0) {
      throw new StepError(`role "${roleName}" not found in org`);
    }
    roleId = records[0].Id;
  } catch (err) {
    if (err instanceof StepError) throw err;
    throw new StepError(`failed to parse role query result for "${roleName}"`);
  }

  const orgResult = spawnSync('sf', [
    'org', 'display',
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  if (orgResult.status !== 0) {
    throw new StepError('failed to resolve current user from org');
  }
  let username;
  try {
    const json = JSON.parse(orgResult.stdout);
    username = json.result?.username;
    if (!username) {
      throw new StepError('could not determine current username from org display');
    }
  } catch (err) {
    if (err instanceof StepError) throw err;
    throw new StepError('failed to parse org display result');
  }

  const userQuery = `SELECT Id, UserRoleId FROM User WHERE Username = '${username}'`;
  const userResult = spawnSync('sf', [
    'data', 'query',
    '--query', userQuery,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  if (userResult.status === 0) {
    try {
      const json = JSON.parse(userResult.stdout);
      const userRecord = json.result?.records?.[0];
      if (userRecord?.UserRoleId) {
        console.log(`  User ${username} already has a role assigned; skipping to avoid overriding.`);
        return;
      }
    } catch { /* continue */ }
  }

  const updateResult = spawnSync('sf', [
    'data', 'update', 'record',
    '--sobject', 'User',
    '--where', `Username='${username}'`,
    '--values', `UserRoleId='${roleId}'`,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  if (updateResult.status === 0) {
    console.log(`  Role "${roleName}" assigned to ${username}.`);
  } else {
    const out = (updateResult.stderr?.toString() || '') + (updateResult.stdout?.toString() || '');
    if (out) console.error(out);
    throw new StepError(`failed to assign role "${roleName}" to ${username}`);
  }
}

/**
 * Query the org for a guest user whose profile name matches the given site name.
 */
function resolveGuestUsername(siteName, targetOrg) {
  const query = `SELECT Username FROM User WHERE Profile.Name LIKE '%${siteName}%' AND UserType = 'Guest'`;
  const result = spawnSync('sf', [
    'data', 'query',
    '--query', query,
    '--target-org', targetOrg,
    '--json',
  ], { cwd: ROOT, encoding: 'utf8' });
  if (result.status !== 0) {
    console.error(`  Failed to query guest user for site "${siteName}".`);
    if (result.stderr) console.error(result.stderr);
    return null;
  }
  try {
    const json = JSON.parse(result.stdout);
    const records = json.result?.records;
    if (!records || records.length === 0) {
      console.error(`  No guest user found for site "${siteName}".`);
      return null;
    }
    return records[0].Username;
  } catch {
    console.error(`  Failed to parse guest user query result for site "${siteName}".`);
    return null;
  }
}

function isOrgConnected(targetOrg) {
  const result = spawnSync('sf', ['org', 'display', '--target-org', targetOrg, '--json'], {
    cwd: ROOT,
    stdio: 'pipe',
    shell: true,
  });
  return result.status === 0;
}

function apexLiteral(value) {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'boolean') return String(value);
  if (typeof value === 'number') return String(value);
  const s = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return `Date.valueOf('${s}')`;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) {
    const dt = s.replace('T', ' ').replace(/\.\d+/, '').replace('Z', '');
    return `DateTime.valueOf('${dt}')`;
  }
  return "'" + s.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
}

function buildApexInsert(sobject, records, refIds) {
  const lines = [
    'Database.DMLOptions dmlOpts = new Database.DMLOptions();',
    'dmlOpts.DuplicateRuleHeader.allowSave = true;',
    `List<${sobject}> recs = new List<${sobject}>();`,
  ];
  for (const rec of records) {
    lines.push(`{ ${sobject} r = new ${sobject}();`);
    for (const [key, val] of Object.entries(rec)) {
      if (key === 'attributes') continue;
      lines.push(`r.put('${key}', ${apexLiteral(val)});`);
    }
    lines.push('recs.add(r); }');
  }
  lines.push('Database.SaveResult[] results = Database.insert(recs, dmlOpts);');
  const refArray = refIds.map((r) => `'${r}'`).join(',');
  lines.push(`String[] refs = new String[]{${refArray}};`);
  lines.push('for (Integer i = 0; i < results.size(); i++) {');
  lines.push("  if (results[i].isSuccess()) System.debug('REF:' + refs[i] + ':' + results[i].getId());");
  lines.push("  else System.debug('ERR:' + refs[i] + ':' + results[i].getErrors()[0].getMessage());");
  lines.push('}');
  return lines.join('\n');
}

/**
 * Interactive multi-select: arrow keys navigate, space toggles, 'a' toggles all, enter confirms.
 * Returns a boolean[] matching the input order.  Falls through immediately when stdin is not a TTY.
 */
async function promptSteps(steps) {
  if (!process.stdin.isTTY) return steps.map((s) => s.enabled);

  // `selected` stays indexed by ORIGINAL step order (so the caller's
  // selections[i] → stepDefs[i] mapping is unchanged); unavailable steps remain
  // false. Only available steps are shown and navigable — unavailable steps are
  // hidden entirely rather than rendered greyed-out.
  const selected = steps.map((s) => s.enabled);
  const visible = steps.map((s, i) => ({ step: s, index: i })).filter(({ step }) => step.available);
  let cursor = 0;
  const RST = '\x1B[0m';
  const CYAN = '\x1B[36m';
  const GREEN = '\x1B[32m';

  /** Strip ANSI escape sequences to get visible character count. */
  function visibleLength(str) {
    return str.replace(/\x1B\[[0-9;]*m/g, '').length;
  }

  /** Count how many terminal rows a set of lines occupies (accounting for wrapping). */
  function terminalRows(lines) {
    const cols = process.stdout.columns || 80;
    let rows = 0;
    for (const line of lines) {
      const len = visibleLength(line);
      rows += len === 0 ? 1 : Math.ceil(len / cols);
    }
    return rows;
  }

  function render() {
    return visible.map(({ step, index }, row) => {
      const ptr = row === cursor ? `${CYAN}❯${RST}` : ' ';
      const chk = selected[index] ? `${GREEN}●${RST}` : '○';
      return `${ptr} ${chk} ${step.label}`;
    });
  }

  let prevRows = 0;

  return new Promise((resolve) => {
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.setEncoding('utf8');
    process.stdout.write('\x1B[?25l');
    console.log('\nSelect steps (↑↓ move, space toggle, a all, enter confirm):\n');
    const initialLines = render();
    prevRows = terminalRows(initialLines);
    process.stdout.write(initialLines.join('\n') + '\n');

    function redraw() {
      process.stdout.write(`\x1B[${prevRows}A`);
      const lines = render();
      for (const line of lines) process.stdout.write(`\x1B[2K${line}\n`);
      prevRows = terminalRows(lines);
    }

    process.stdin.on('data', (key) => {
      if (key === '\x03') {
        process.stdout.write('\x1B[?25h\n');
        process.exit(0);
      }
      if (key === '\r' || key === '\n') {
        process.stdout.write('\x1B[?25h');
        process.stdin.setRawMode(false);
        process.stdin.pause();
        process.stdin.removeAllListeners('data');
        console.log();
        resolve(selected);
        return;
      }
      // Note: `cursor` indexes `visible`; `selected` is indexed by ORIGINAL step
      // order. Map through visible[cursor].index before touching `selected`.
      if (key === ' ') {
        const { index } = visible[cursor];
        selected[index] = !selected[index];
        redraw();
        return;
      }
      if (key === 'a') {
        const allOn = visible.every(({ index }) => selected[index]);
        for (const { index } of visible) selected[index] = !allOn;
        redraw();
        return;
      }
      if (key === '\x1B[A' || key === 'k') {
        cursor = Math.max(0, cursor - 1);
        redraw();
      } else if (key === '\x1B[B' || key === 'j') {
        cursor = Math.min(visible.length - 1, cursor + 1);
        redraw();
      }
    });
  });
}

function run(name, cmd, args, opts = {}) {
  const { cwd = ROOT, optional = false } = opts;
  console.log('\n---', name, '---');
  const result = spawnSync(cmd, args, {
    cwd,
    stdio: 'inherit',
    shell: true,
    ...(opts.env && { env: opts.env }),
    ...(opts.timeout && { timeout: opts.timeout }),
  });
  if (result.status !== 0 && !optional) {
    throw new StepError(`${name} (exit ${result.status ?? 1})`);
  }
  return result;
}

/** Promise-based spawn for parallel execution. Always uses stdio: 'pipe'. */
function spawnAsync(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const proc = nodeSpawn(cmd, args, {
      cwd: opts.cwd || ROOT,
      stdio: 'pipe',
      shell: true,
      ...(opts.timeout && { timeout: opts.timeout }),
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => { stdout += d.toString(); });
    proc.stderr.on('data', (d) => { stderr += d.toString(); });
    proc.on('close', (code) => resolve({ status: code, stdout, stderr }));
    proc.on('error', reject);
  });
}

/** Async version of run() for parallel steps. Captures output and prints on failure. */
async function runAsync(name, cmd, args, opts = {}) {
  const { cwd = ROOT, optional = false } = opts;
  const result = await spawnAsync(cmd, args, { cwd, ...(opts.timeout && { timeout: opts.timeout }) });
  if (result.status !== 0 && !optional) {
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    throw new StepError(`${name} (exit ${result.status ?? 1})`);
  }
  return result;
}

/**
 * In-memory result ledger. Each selected step records exactly one outcome:
 *   ok      — the step ran and succeeded
 *   skipped — the step was not selected, or had no config section (intentional)
 *   failed  — the step ran and failed (with a human-readable reason)
 * The end-of-run summary is rendered from this ledger and the process exits
 * non-zero whenever any step is `failed` (fail-fast or skippable alike).
 *
 * @typedef {{ key: string, label: string, status: 'ok'|'skipped'|'failed', reason?: string, failFast?: boolean }} StepResult
 */
const results = [];
function recordOk(step) {
  results.push({ key: step.key, label: step.label, status: 'ok', failFast: step.failFast });
}
function recordSkipped(step, reason) {
  results.push({ key: step.key, label: step.label, status: 'skipped', reason, failFast: step.failFast });
}
function recordFailed(step, reason) {
  results.push({ key: step.key, label: step.label, status: 'failed', reason, failFast: step.failFast });
}

/** True if any step in the ledger failed. */
function finalExitCode() {
  return results.some((r) => r.status === 'failed') ? 1 : 0;
}

const SUMMARY_GLYPH = { ok: '✔', skipped: '–', failed: '✖' };

/**
 * Render the end-of-run summary. Always called — on success, on a fail-fast
 * abort (partial: only steps reached so far are present), and on a clean finish
 * that had skippable failures. Failed rows are listed last so the real problem
 * is the last thing the developer sees.
 */
function printSummary(targetOrg) {
  const ordered = [
    ...results.filter((r) => r.status !== 'failed'),
    ...results.filter((r) => r.status === 'failed'),
  ];
  const pad = Math.max(0, ...ordered.map((r) => r.key.length));
  console.log(`\nSetup summary (target org: ${targetOrg})`);
  for (const r of ordered) {
    const glyph = SUMMARY_GLYPH[r.status] ?? ' ';
    const key = r.key.padEnd(pad);
    let line = `  ${glyph} ${key}  ${r.status}`;
    if (r.reason) line += ` (${r.reason})`;
    if (r.status === 'failed') line += r.failFast ? '   [fail-fast — aborted]' : '   [skippable — continued]';
    console.log(line);
  }
  const failures = results.filter((r) => r.status === 'failed').length;
  if (failures > 0) {
    console.log(`Setup completed with ${failures} failure(s). Exiting 1.`);
  } else {
    console.log('Setup complete.');
  }
}

/**
 * Run one step body, recording its outcome in the ledger and honoring the
 * step's fixed `failFast` classification. The body either completes (→ ok),
 * throws a StepError (→ failed), or throws something unexpected (→ failed,
 * with the raw message). On a fail-fast failure this prints the partial
 * summary and exits non-zero immediately; on a skippable failure it records
 * and returns so the run continues.
 */
async function runStep(step, targetOrg, body) {
  try {
    await body();
    recordOk(step);
  } catch (err) {
    const reason = err instanceof StepError ? err.message : (err?.message ?? String(err));
    recordFailed(step, reason);
    console.error(`\nStep "${step.key}" failed: ${reason}`);
    if (step.failFast) {
      printSummary(targetOrg);
      process.exit(1);
    }
  }
}

async function main() {
  // Ensure .gitignore files exist (npm strips them from published packages).
  const gitignoreTemplates = loadGitignoreTemplates();
  if (gitignoreTemplates) {
    ensureGitignore(ROOT, gitignoreTemplates.sfdx);
    if (existsSync(UIBUNDLES_DIR)) {
      for (const entry of readdirSync(UIBUNDLES_DIR, { withFileTypes: true })) {
        if (entry.isDirectory() && !entry.name.startsWith('.')) {
          ensureGitignore(resolve(UIBUNDLES_DIR, entry.name), gitignoreTemplates.webapp);
        }
      }
    }
  }

  const {
    targetOrg,
    uiBundleName,
    permsetNamesExplicit,
    yes,
    skipLogin: argSkipLogin,
    skipDeploy: argSkipDeploy,
    skipPermset: argSkipPermset,
    skipRole: argSkipRole,
    skipSelfReg: argSkipSelfReg,
    skipData: argSkipData,
    skipGraphql: argSkipGraphql,
    skipUIBundleBuild: argSkipUIBundleBuild,
    skipDev: argSkipDev,
  } = parseArgs();

  const permsetNames =
    permsetNamesExplicit.length > 0 ? permsetNamesExplicit : discoverPermissionSetNames();
  const permsetStepLabel =
    permsetNames.length === 0
      ? 'Permset — (none under permissionsets/)'
      : permsetNames.length <= 3
        ? `Permset — assign ${permsetNames.join(', ')}`
        : `Permset — assign ${permsetNames.length} permission sets`;

  // Validate org-setup.config.json ONCE, before any step runs (spec §5.2). The
  // three load*Config helpers read from this already-validated object.
  const config = loadValidatedConfig();

  const hasDataPlan = existsSync(DATA_PLAN) && existsSync(DATA_DIR);
  const roleConfig = loadRoleConfig(config);
  const hasRoleConfig = roleConfig !== null;
  const selfRegConfig = loadSelfRegConfig(config);
  const hasSelfRegConfig = selfRegConfig !== null;

  // failFast is a fixed, implementer-owned classification (spec §5.2) — NOT
  // user-configurable. A fail-fast failure aborts the run immediately; a
  // skippable failure is recorded and the run continues. The exit code is
  // non-zero on any failure regardless of class.
  const stepDefs = [
    { key: 'login', label: 'Login — org authentication', enabled: !argSkipLogin, available: true, failFast: true },
    { key: 'uiBundleBuild', label: 'UI Bundle Build — npm install + build (pre-deploy)', enabled: !argSkipUIBundleBuild, available: true, failFast: true },
    { key: 'deploy', label: 'Deploy — sf project deploy start', enabled: !argSkipDeploy, available: true, failFast: true },
    { key: 'permset', label: permsetStepLabel, enabled: !argSkipPermset, available: true, failFast: false },
    { key: 'role', label: `Role — assign "${roleConfig?.roleName ?? '?'}" to current user`, enabled: !argSkipRole && hasRoleConfig, available: hasRoleConfig, failFast: false },
    { key: 'selfReg', label: 'Self-Registration — enable for site', enabled: !argSkipSelfReg && hasSelfRegConfig, available: hasSelfRegConfig, failFast: false },
    { key: 'data', label: 'Data — delete + import records via Apex', enabled: !argSkipData && hasDataPlan, available: hasDataPlan, failFast: true },
    { key: 'graphql', label: 'GraphQL — schema introspect + codegen', enabled: !argSkipGraphql, available: true, failFast: true },
    { key: 'dev', label: 'Dev — launch dev server', enabled: !argSkipDev, available: true, failFast: false },
  ];

  const selections = yes ? stepDefs.map((s) => s.enabled) : await promptSteps(stepDefs);
  const on = {};
  stepDefs.forEach((s, i) => {
    on[s.key] = selections[i];
  });

  const skipLogin = !on.login;
  const skipUIBundleBuild = !on.uiBundleBuild;
  const skipDeploy = !on.deploy;
  const skipPermset = !on.permset;
  const skipRole = !on.role;
  const skipSelfReg = !on.selfReg;
  const skipData = !on.data;
  const skipGraphql = !on.graphql;
  const skipDev = !on.dev;

  const needsUIBundle = !skipUIBundleBuild || !skipGraphql || !skipDev;
  const uiBundleDir = needsUIBundle ? discoverUIBundleDir(uiBundleName) : null;
  const doData = !skipData;

  console.log('Setup — target org:', targetOrg, '| UI bundle:', uiBundleDir ?? '(none)');
  console.log(
    'Steps: login=%s deploy=%s permset=%s role=%s selfReg=%s data=%s graphql=%s uiBundle=%s dev=%s',
    !skipLogin,
    !skipDeploy,
    !skipPermset,
    !skipRole,
    !skipSelfReg,
    doData,
    !skipGraphql,
    !skipUIBundleBuild,
    !skipDev
  );

  const loginStep = stepDefs.find((s) => s.key === 'login');
  if (!skipLogin) {
    await runStep(loginStep, targetOrg, async () => {
      if (isOrgConnected(targetOrg)) {
        console.log('\n--- Login ---');
        console.log(`Org ${targetOrg} is already authenticated; skipping browser login.`);
      } else {
        // Login is fail-fast (spec §5.2): drop the previous { optional: true } so a
        // failed browser login records `failed`, prints the summary, and aborts.
        run('Login (browser)', 'sf', ['org', 'login', 'web', '--alias', targetOrg]);
      }
    });
  } else {
    recordSkipped(loginStep, 'not selected');
  }

  // Ensure the self-reg profile is in networkMemberGroups before deploy so that
  // subsequent selfRegProfile / selfRegistration updates don't fail. This is
  // best-effort prep: if the site can't be derived (no network file, or the
  // ambiguous multi-network case where deriveSiteName throws), skip the prep
  // silently here — the selfReg step records that derivation failure as a
  // skippable StepError, so it stays in the ledger instead of aborting pre-deploy.
  if (!skipDeploy && selfRegConfig) {
    let preDeploySiteName = null;
    try {
      preDeploySiteName = deriveSiteName();
    } catch {
      // ambiguous derivation — surfaced by the selfReg step below
    }
    if (preDeploySiteName) {
      console.log('\n--- Ensure network member profile (pre-deploy) ---');
      ensureNetworkMemberProfile(selfRegConfig, preDeploySiteName);
    }
  }

  // Build all UI Bundles before deploy so dist exists for entity deployment
  const uiBundleBuildStep = stepDefs.find((s) => s.key === 'uiBundleBuild');
  let preDeployBundlesBuilt = false;
  if (!skipUIBundleBuild) {
    if (!skipDeploy) {
      await runStep(uiBundleBuildStep, targetOrg, () => {
        const allUIBundleDirs = discoverAllUIBundleDirs(uiBundleName);
        for (const dir of allUIBundleDirs) {
          const name = dir.split(/[/\\]/).pop();
          run(`UI Bundle install (${name})`, 'npm', ['install'], { cwd: dir });
          run(`UI Bundle build (${name})`, 'npm', ['run', 'build'], { cwd: dir });
        }
      });
      preDeployBundlesBuilt = true;
    }
    // When skipDeploy, the bundle build happens in the GraphQL section below;
    // its outcome is recorded there.
  } else {
    recordSkipped(uiBundleBuildStep, 'not selected');
  }

  const deployStep = stepDefs.find((s) => s.key === 'deploy');
  if (!skipDeploy) {
    await runStep(deployStep, targetOrg, () => {
      run('Deploy metadata', 'sf', ['project', 'deploy', 'start', '--target-org', targetOrg], {
        timeout: 180000,
      });
    });
  } else {
    recordSkipped(deployStep, 'not selected');
  }

  const permsetStep = stepDefs.find((s) => s.key === 'permset');
  if (!skipPermset) {
    await runStep(permsetStep, targetOrg, async () => {
      const permsetConfig = loadPermsetConfig(config);
      if (permsetNames.length === 0) {
        console.log('\n--- Assign permission sets ---');
        console.log('No permission sets found under permissionsets/ and none passed via --permset-name; skipping.');
        return;
      }
      console.log('\n--- Assign permission sets ---');

      // Resolve assignments (guest user lookups etc.) then run all sf assign calls in parallel.
      //
      // A guest-user resolution failure (no derivable site, or no guest user yet)
      // is collected — NOT thrown mid-loop. Throwing here would unwind the whole
      // runStep body before Promise.all and silently drop every assignment already
      // queued (e.g. a currentUser permset that sorts ahead of a guestUser one and
      // never depended on the site at all). Resolvable assignments still run; the
      // combined failure is thrown at the end so the step is still recorded failed.
      const assignmentJobs = [];
      const resolutionFailures = [];
      for (const permsetName of permsetNames) {
        const assignment = resolveAssignment(permsetName, permsetConfig);
        if (assignment.assignee === 'skip') {
          console.log(`Permission set "${permsetName}" — skipped (config).`);
          continue;
        }
        let effectiveUsername = null;
        if (assignment.assignee === 'guestUser') {
          // Site name is derived from the single network metadata file the app
          // ships (spec §5.2) — never restated per-assignment.
          const siteName = deriveSiteName();
          if (!siteName) {
            console.error(`Permission set "${permsetName}" — assignee is "guestUser" but no networks/<siteName>.network-meta.xml was found to derive the site; skipping.`);
            resolutionFailures.push(`${permsetName} (no network metadata to derive site)`);
            continue;
          }
          effectiveUsername = resolveGuestUsername(siteName, targetOrg);
          if (!effectiveUsername) {
            console.error(`Permission set "${permsetName}" — could not resolve guest user for site "${siteName}"; skipping.`);
            resolutionFailures.push(`${permsetName} (could not resolve guest user for site "${siteName}")`);
            continue;
          }
          console.log(`  Resolved guest user for site "${siteName}": ${effectiveUsername}`);
        }
        assignmentJobs.push({ permsetName, effectiveUsername });
      }

      // Run all permset assignment calls in parallel.
      const assignResults = await Promise.all(assignmentJobs.map(async ({ permsetName, effectiveUsername }) => {
        const sfArgs = ['org', 'assign', 'permset', '--name', permsetName, '--target-org', targetOrg];
        if (effectiveUsername) {
          sfArgs.push('--on-behalf-of', effectiveUsername);
        }
        const assigneeLabel = effectiveUsername || 'current user';
        const result = await spawnAsync('sf', sfArgs);
        return { permsetName, assigneeLabel, result };
      }));

      const failures = [];
      for (const { permsetName, assigneeLabel, result } of assignResults) {
        if (result.status === 0) {
          console.log(`Permission set "${permsetName}" assigned to ${assigneeLabel}.`);
        } else {
          const out = (result.stderr || '') + (result.stdout || '');
          if (out.includes('Duplicate') && out.includes('PermissionSet')) {
            console.log(`Permission set "${permsetName}" already assigned to ${assigneeLabel}; skipping.`);
          } else if (out.includes('not found') && out.includes('target org')) {
            console.log(`Permission set "${permsetName}" not in org; skipping.`);
          } else {
            if (result.stdout) process.stdout.write(result.stdout);
            if (result.stderr) process.stderr.write(result.stderr);
            failures.push(`${permsetName} (exit ${result.status ?? 1})`);
          }
        }
      }
      const allFailures = [...resolutionFailures, ...failures];
      if (allFailures.length > 0) {
        throw new StepError(`failed to assign permission set(s): ${allFailures.join(', ')}`);
      }
    });
  } else {
    recordSkipped(permsetStep, 'not selected');
  }

  const roleStep = stepDefs.find((s) => s.key === 'role');
  if (!skipRole) {
    console.log('\n--- Assign role ---');
    // Config shape (assignee === 'currentUser', non-empty roleName) is guaranteed
    // by the schema, so there is nothing to re-check here — the step either ran
    // (ok) or its assignment threw (failed). No manual recordSkipped inference.
    await runStep(roleStep, targetOrg, () => {
      assignRoleToCurrentUser(roleConfig.roleName, targetOrg);
    });
  } else {
    recordSkipped(roleStep, roleStep.available ? 'not selected' : 'no config');
  }

  const selfRegStep = stepDefs.find((s) => s.key === 'selfReg');
  if (!skipSelfReg) {
    console.log('\n--- Enable self-registration ---');
    // Config shape (selfRegProfile, accountName) is guaranteed by the schema.
    // The site is derived inside the step body so a "multiple network files"
    // StepError is recorded in the ledger rather than escaping. No manual
    // recordSkipped inference.
    await runStep(selfRegStep, targetOrg, () => {
      const siteName = deriveSiteName();
      if (!siteName) {
        throw new StepError(
          'self-registration is configured but no networks/<siteName>.network-meta.xml was found to derive the site',
        );
      }
      enableSelfRegistration(selfRegConfig, siteName, targetOrg);
    });
  } else {
    recordSkipped(selfRegStep, selfRegStep.available ? 'not selected' : 'no config');
  }

  const dataStep = stepDefs.find((s) => s.key === 'data');
  if (doData) {
   await runStep(dataStep, targetOrg, () => {
    // Prepare data for uniqueness (run before import so repeat imports don't conflict)
    const prepareScript = resolve(__dirname, 'prepare-import-unique-fields.js');
    run('Prepare data (unique fields)', 'node', [prepareScript, '--data-dir', DATA_DIR], {
      cwd: ROOT,
    });
    // Normalize Lease__c Tenant refs to 1–15 so all refs resolve (Tenant__c.json has 15 records)
    const leasePath = resolve(DATA_DIR, 'Lease__c.json');
    if (existsSync(leasePath)) {
      let leaseContent = readFileSync(leasePath, 'utf8');
      leaseContent = leaseContent.replace(/@TenantRef(\d+)/g, (_m, n) => {
        const k = ((parseInt(n, 10) - 1) % 15) + 1;
        return `@TenantRef${k}`;
      });
      writeFileSync(leasePath, leaseContent);
    }

    // Delete existing records so every run inserts the full dataset without duplicate conflicts.
    // Reverse plan order ensures children are removed before parents (FK safety).
    console.log('\n--- Clean existing data for fresh import ---');
    const planEntries = JSON.parse(readFileSync(DATA_PLAN, 'utf8'));
    const sobjectsReversed = [...planEntries.map((e) => e.sobject)].reverse();
    const tmpApex = resolve(ROOT, '.tmp-setup-delete.apex');
    for (const sobject of sobjectsReversed) {
      const apexCode = [
        'try {',
        `  List<SObject> recs = Database.query('SELECT Id FROM ${sobject} LIMIT 10000');`,
        '  if (!recs.isEmpty()) {',
        '    Database.delete(recs, false);',
        '    Database.emptyRecycleBin(recs);',
        '  }',
        '} catch (Exception e) {',
        '  // non-deletable records (e.g. Contact linked to Case) are skipped via allOrNone=false',
        '}',
      ].join('\n');
      writeFileSync(tmpApex, apexCode);
      spawnSync('sf', ['apex', 'run', '--target-org', targetOrg, '--file', tmpApex], {
        cwd: ROOT,
        stdio: 'pipe',
        shell: true,
        timeout: 60000,
      });
      console.log(`  ${sobject}: cleaned`);
    }
    if (existsSync(tmpApex)) unlinkSync(tmpApex);

    // Import via Anonymous Apex with Database.DMLOptions.duplicateRuleHeader.allowSave = true.
    // This bypasses both duplicate-rule blocks AND matching-service timeouts that the REST
    // API headers (Sforce-Duplicate-Rule-Action) cannot override.
    console.log('\n--- Data import tree ---');
    const refMap = new Map();
    const APEX_CHAR_LIMIT = 25000;
    const APEX_MAX_BATCH = 200;

    for (const entry of planEntries) {
      for (const file of entry.files) {
        const data = JSON.parse(readFileSync(resolve(DATA_DIR, file), 'utf8'));
        const records = data.records || [];

        for (const rec of records) {
          for (const key of Object.keys(rec)) {
            if (key === 'attributes') continue;
            const val = rec[key];
            if (typeof val === 'string' && val.startsWith('@')) {
              const actual = refMap.get(val.slice(1));
              if (actual) {
                rec[key] = actual;
              } else if (refMap.size > 0) {
                console.warn(`    Warning: unresolved ref ${val} in ${file}`);
              }
            }
          }
        }

        let imported = 0;
        const sampleRec = records[0] || {};
        const fieldsPerRec = Object.keys(sampleRec).filter((k) => k !== 'attributes').length;
        const estCharsPerRec = 40 + fieldsPerRec * 55;
        const batchSize = Math.min(APEX_MAX_BATCH, Math.max(5, Math.floor(APEX_CHAR_LIMIT / estCharsPerRec)));
        for (let i = 0; i < records.length; i += batchSize) {
          const batch = records.slice(i, i + batchSize);
          const refIds = batch.map((r) => r.attributes?.referenceId || `_idx${i}`);
          const apex = buildApexInsert(entry.sobject, batch, refIds);
          writeFileSync(tmpApex, apex);
          const apexResult = spawnSync(
            'sf',
            ['apex', 'run', '--target-org', targetOrg, '--file', tmpApex],
            { cwd: ROOT, stdio: 'pipe', shell: true, timeout: 120000 }
          );
          const apexOut = apexResult.stdout?.toString() || '';
          const apexErr = apexResult.stderr?.toString() || '';
          if (apexResult.status !== 0 && !apexOut.includes('Compiled successfully')) {
            process.stderr.write(apexErr || apexOut);
            throw new StepError(`${entry.sobject}: apex execution failed`);
          }
          const okMatches = [...apexOut.matchAll(/\|DEBUG\|REF:([^:\n]+):(\w+)/g)];
          const errMatches = [...apexOut.matchAll(/\|DEBUG\|ERR:([^:\n]+):([^\n]+)/g)];
          if (errMatches.length) {
            for (const m of errMatches.slice(0, 5)) {
              console.error(`    ${m[1]}: ${m[2].trim()}`);
            }
            if (errMatches.length > 5) console.error(`    ... and ${errMatches.length - 5} more`);
            throw new StepError(`data import tree (${entry.sobject}) — ${errMatches.length} record error(s)`);
          }
          if (entry.saveRefs) {
            for (const m of okMatches) refMap.set(m[1], m[2]);
          }
          imported += okMatches.length;
        }
        console.log(`  ${entry.sobject}: imported ${imported} records`);
      }
    }
    if (existsSync(tmpApex)) unlinkSync(tmpApex);
   });
  } else {
    recordSkipped(dataStep, dataStep.available ? 'not selected' : 'no data plan');
  }

  const graphqlStep = stepDefs.find((s) => s.key === 'graphql');
  if (!skipGraphql) {
    await runStep(graphqlStep, targetOrg, () => {
      run('UI Bundle npm install', 'npm', ['install'], { cwd: uiBundleDir });
      run('GraphQL schema (introspect)', 'npm', ['run', 'graphql:schema'], {
        cwd: uiBundleDir,
        env: { ...process.env, SF_TARGET_ORG: targetOrg },
      });
      run('GraphQL codegen', 'npm', ['run', 'graphql:codegen'], { cwd: uiBundleDir });
      run('UI Bundle build (post-codegen)', 'npm', ['run', 'build'], { cwd: uiBundleDir });
    });
  } else {
    recordSkipped(graphqlStep, 'not selected');
    if (!skipUIBundleBuild && skipDeploy && !preDeployBundlesBuilt) {
      // The pre-deploy build never ran (deploy was skipped); build here and
      // record the uiBundleBuild outcome that the pre-deploy branch would have.
      await runStep(uiBundleBuildStep, targetOrg, () => {
        run('UI Bundle npm install', 'npm', ['install'], { cwd: uiBundleDir });
        run('UI Bundle build', 'npm', ['run', 'build'], { cwd: uiBundleDir });
      });
      preDeployBundlesBuilt = true;
    }
  }

  // When uiBundleBuild was selected but the dedicated pre-deploy build never ran
  // (deploy skipped and graphql selected), the build happened inside the graphql
  // step — which is fail-fast, so reaching here means it succeeded. Record ok.
  if (!skipUIBundleBuild && !preDeployBundlesBuilt && !results.some((r) => r.key === 'uiBundleBuild')) {
    recordOk(uiBundleBuildStep);
  }

  const devStep = stepDefs.find((s) => s.key === 'dev');
  if (!skipDev) {
    // dev is skippable and terminal: a failure here is a local runtime issue
    // (port in use, tooling), not a broken setup. Print the summary BEFORE the
    // (blocking, long-lived) dev server starts so the developer sees the setup
    // outcome up front; the server then runs in the foreground until Ctrl+C.
    recordOk(devStep);
    printSummary(targetOrg);
    console.log('\n--- Launching dev server (Ctrl+C to stop) ---\n');
    const devResult = run('Dev server', 'npm', ['run', 'dev'], { cwd: uiBundleDir, optional: true });
    if (devResult.status !== 0) {
      // Replace the optimistic `ok` with a skippable failure and reprint.
      const row = results.find((r) => r.key === 'dev');
      row.status = 'failed';
      row.reason = 'dev server failed to start — setup itself completed; check local runtime';
      printSummary(targetOrg);
    }
    process.exit(finalExitCode());
  } else {
    recordSkipped(devStep, 'not selected');
  }

  printSummary(targetOrg);
  process.exit(finalExitCode());
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
