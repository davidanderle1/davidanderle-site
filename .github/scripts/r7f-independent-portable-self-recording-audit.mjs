#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';

const [builderArg, verifierArg, tupleArg, outputArg] = process.argv.slice(2);
if (!builderArg || !verifierArg || !tupleArg || !outputArg) {
  throw new Error('usage: auditor BUILDER_ROOT VERIFIER_ROOT R7E_TUPLE_JSON OUTPUT_JSON');
}

const builder = path.resolve(builderArg);
const verifier = path.resolve(verifierArg);
const tuplePath = path.resolve(tupleArg);
const output = path.resolve(outputArg);
const req = createRequire(path.join(verifier, 'package.json'));
const AjvModule = req('ajv/dist/2020.js');
const Ajv2020 = AjvModule.default ?? AjvModule;

const shaBytes = (value) => crypto.createHash('sha256').update(value).digest('hex');
const shaFile = (file) => shaBytes(fs.readFileSync(file));
const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const listFiles = (dir, suffix) => {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { recursive: true })
    .filter((entry) => typeof entry === 'string' && entry.endsWith(suffix))
    .sort()
    .map((entry) => path.join(dir, entry));
};
const parseFrontmatter = (file) => {
  const text = fs.readFileSync(file, 'utf8');
  if (!text.startsWith('---\n')) throw new Error(`missing frontmatter: ${file}`);
  const end = text.indexOf('\n---\n', 4);
  if (end < 0) throw new Error(`unterminated frontmatter: ${file}`);
  const out = {};
  for (const line of text.slice(4, end).split('\n')) {
    if (!line.trim()) continue;
    const colon = line.indexOf(':');
    if (colon < 1) throw new Error(`invalid frontmatter line: ${file}: ${line}`);
    out[line.slice(0, colon).trim()] = JSON.parse(line.slice(colon + 1).trim());
  }
  return out;
};

const builderSource = path.join(builder, 'BEARING_PRODUCTION_SOURCE');
const verifierSource = verifier;
const schemaNames = [
  'canonical-content.schema.json',
  'index.json',
  'milestone.schema.json',
  'profile.schema.json',
  'public-document.schema.json',
  'redirect-record.schema.json',
  'tombstone-record.schema.json',
  'work-record.schema.json',
  'writing-record.schema.json',
];
const contractSchemaNames = schemaNames.filter((name) => name !== 'index.json');
const builderSchemaDir = path.join(builderSource, 'schemas');
const verifierSchemaDir = path.join(verifierSource, 'schemas');
const checks = {};
const errors = [];

const actualBuilderSchemas = fs.readdirSync(builderSchemaDir).filter((name) => name.endsWith('.json')).sort();
const actualVerifierSchemas = fs.readdirSync(verifierSchemaDir).filter((name) => name.endsWith('.json')).sort();
checks['builder-schema-set-exact'] = JSON.stringify(actualBuilderSchemas) === JSON.stringify(schemaNames);
checks['verifier-schema-set-exact'] = JSON.stringify(actualVerifierSchemas) === JSON.stringify(schemaNames);
checks['builder-verifier-schema-byte-parity'] = schemaNames.every(
  (name) => fs.readFileSync(path.join(builderSchemaDir, name)).equals(fs.readFileSync(path.join(verifierSchemaDir, name))),
);
checks['typed-schema-source-byte-parity'] =
  fs.readFileSync(path.join(builderSource, 'src/content-schemas.ts')).equals(
    fs.readFileSync(path.join(verifierSource, 'src/content-schemas.ts')),
  );
checks['schema-generator-byte-parity'] =
  fs.readFileSync(path.join(builderSource, 'scripts/generate-json-schemas.mjs')).equals(
    fs.readFileSync(path.join(verifierSource, 'scripts/generate-json-schemas.mjs')),
  );

const schemas = Object.fromEntries(schemaNames.map((name) => [name, readJson(path.join(verifierSchemaDir, name))]));
const index = schemas['index.json'];
checks['draft-2020-12-index'] =
  index.$schema === 'https://json-schema.org/draft/2020-12/schema' &&
  index.contractVersion === '1.0.0' &&
  index.source === 'src/content-schemas.ts' &&
  Array.isArray(index.schemas) &&
  index.schemas.length === 8;
checks['draft-2020-12-contracts'] = contractSchemaNames.every((name) => {
  const schema = schemas[name];
  return schema.$schema === 'https://json-schema.org/draft/2020-12/schema' &&
    schema['x-contract-version'] === '1.0.0' &&
    schema['x-source'] === 'src/content-schemas.ts' &&
    typeof schema.$id === 'string' &&
    schema.$id.startsWith('https://davidanderle.com/schemas/');
});

const ajv = new Ajv2020({ allErrors: true, strict: true, validateFormats: false });
ajv.addKeyword({ keyword: 'x-contract-version', schemaType: 'string', valid: true });
ajv.addKeyword({ keyword: 'x-source', schemaType: 'string', valid: true });
for (const name of contractSchemaNames) ajv.addSchema(schemas[name]);
const validators = Object.fromEntries(
  contractSchemaNames.map((name) => [name, ajv.getSchema(schemas[name].$id)]),
);
checks['all-eight-schemas-compiled'] = Object.values(validators).every((validator) => typeof validator === 'function');

const content = path.join(verifierSource, 'src/content');
const groups = {
  profile: listFiles(path.join(content, 'profile'), '.json').map(readJson),
  work: listFiles(path.join(content, 'work'), '.md').map(parseFrontmatter),
  writing: listFiles(path.join(content, 'writing'), '.md').map(parseFrontmatter),
  milestone: readJson(path.join(content, 'milestones.json')),
  publicDocument: readJson(path.join(content, 'public-documents.json')),
  redirect: readJson(path.join(content, 'redirects.json')),
  tombstone: readJson(path.join(content, 'tombstones.json')),
};
const mapping = {
  profile: 'profile.schema.json',
  work: 'work-record.schema.json',
  writing: 'writing-record.schema.json',
  milestone: 'milestone.schema.json',
  publicDocument: 'public-document.schema.json',
  redirect: 'redirect-record.schema.json',
  tombstone: 'tombstone-record.schema.json',
};
let recordCount = 0;
for (const [group, rows] of Object.entries(groups)) {
  const schemaName = mapping[group];
  const validator = validators[schemaName];
  for (const [indexValue, row] of rows.entries()) {
    recordCount += 1;
    if (!validator(row)) {
      errors.push({
        code: 'RECORD_SCHEMA_FAILURE',
        group,
        index: indexValue,
        schema: schemaName,
        errors: structuredClone(validator.errors ?? []),
      });
    }
  }
}
checks['canonical-record-count-12'] = recordCount === 12;
checks['all-records-independent-ajv-valid'] = !errors.some((row) => row.code === 'RECORD_SCHEMA_FAILURE');

const corpus = {
  schemaVersion: '1.0.0',
  profile: groups.profile,
  work: groups.work,
  writing: groups.writing,
  milestones: groups.milestone,
  publicDocuments: groups.publicDocument,
  redirects: groups.redirect,
  tombstones: groups.tombstone,
};
const corpusValidator = validators['canonical-content.schema.json'];
checks['canonical-corpus-independent-ajv-valid'] = Boolean(corpusValidator(corpus));
if (!checks['canonical-corpus-independent-ajv-valid']) {
  errors.push({ code: 'CORPUS_SCHEMA_FAILURE', errors: structuredClone(corpusValidator.errors ?? []) });
}

const invalidMissing = structuredClone(groups.profile[0]);
delete invalidMissing.immutableId;
checks['negative-missing-required-rejected'] = validators['profile.schema.json'](invalidMissing) === false;
const invalidUnknown = { ...structuredClone(groups.profile[0]), __r7fUnknownProperty: true };
checks['negative-unknown-property-rejected'] = validators['profile.schema.json'](invalidUnknown) === false;
const mutatedSchema = structuredClone(schemas['profile.schema.json']);
mutatedSchema.title = 'R7F MUTATED SCHEMA';
checks['negative-stale-schema-byte-drift-rejected'] =
  Buffer.from(`${JSON.stringify(mutatedSchema, null, 2)}\n`).equals(
    fs.readFileSync(path.join(verifierSchemaDir, 'profile.schema.json')),
  ) === false;

const tuple = readJson(tuplePath);
const packageValidation = readJson(path.join(builder, 'R7E_PACKAGE_VALIDATION.json'));
const selfValidation = readJson(path.join(builder, 'R7E_SELF_RECORDING_VALIDATION.json'));
const execution = readJson(path.join(builder, 'R7E_EXECUTOR_EVIDENCE/generated-plan-execution.json'));
const identity = readJson(path.join(builder, 'R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json'));

const expected = {
  repository: process.env.GITHUB_REPOSITORY,
  branch: process.env.BUILDER_BRANCH,
  workflowPath: process.env.BUILDER_WORKFLOW_PATH,
  commit: process.env.BUILDER_COMMIT,
  runId: Number(process.env.BUILDER_RUN_ID),
  artifactId: Number(process.env.BUILDER_ARTIFACT_ID),
  artifactName: process.env.BUILDER_ARTIFACT_NAME,
  artifactDigest: process.env.BUILDER_ARTIFACT_DIGEST,
  tupleArtifactId: Number(process.env.BUILDER_TUPLE_ARTIFACT_ID),
  tupleArtifactName: process.env.BUILDER_TUPLE_ARTIFACT_NAME,
  tupleArtifactDigest: process.env.BUILDER_TUPLE_ARTIFACT_DIGEST,
  sourceArchive: process.env.BUILDER_SOURCE_ARCHIVE_SHA256,
  generatedPlan: process.env.BUILDER_GENERATED_PLAN_SHA256,
};

const authenticTuple = (candidate) =>
  candidate?.schema === 'R7E_PORTABLE_SELF_RECORDING_AUTHORITATIVE_TUPLE_V3' &&
  candidate?.passed === true &&
  candidate?.repository === expected.repository &&
  candidate?.branch === expected.branch &&
  candidate?.workflowPath === expected.workflowPath &&
  candidate?.commit === expected.commit &&
  candidate?.runId === expected.runId &&
  candidate?.artifact?.id === expected.artifactId &&
  candidate?.artifact?.name === expected.artifactName &&
  candidate?.artifact?.digest === expected.artifactDigest &&
  candidate?.sourceArchiveSha256 === expected.sourceArchive &&
  candidate?.generatedPlanSha256 === expected.generatedPlan &&
  candidate?.scope === 'R7 technical architecture only' &&
  candidate?.mainMutationAuthorized === false &&
  candidate?.productionDeploymentAuthorized === false;

checks['authentic-r7e-tuple'] = authenticTuple(tuple);
const mutatedTuple = structuredClone(tuple);
mutatedTuple.artifact.digest = `sha256:${'0'.repeat(64)}`;
checks['negative-mutated-tuple-rejected'] = authenticTuple(mutatedTuple) === false;

checks['builder-package-validation-pass'] =
  packageValidation.passed === true &&
  Array.isArray(packageValidation.failedChecks) &&
  packageValidation.failedChecks.length === 0 &&
  Object.values(packageValidation.checks ?? {}).every((value) => value === true);
checks['builder-self-recording-validation-pass'] =
  selfValidation.schema === 'R7E_SELF_RECORDING_EXECUTOR_VALIDATION_V3' &&
  selfValidation.passed === true &&
  Array.isArray(selfValidation.failedChecks) &&
  selfValidation.failedChecks.length === 0 &&
  Object.values(selfValidation.checks ?? {}).every((value) => value === true) &&
  selfValidation.mainMutationAuthorized === false &&
  selfValidation.productionDeploymentAuthorized === false;
checks['builder-generated-plan-execution-pass'] =
  execution.schema === 'R7E_GENERATED_PLAN_EXECUTION_V2' &&
  execution.passed === true &&
  execution.firstFailure === null &&
  execution.executedRunStepCount === 18 &&
  execution.skippedAllowedUsesCount === 3 &&
  execution.skippedConditionCount === 1;
checks['builder-identity-bound-to-tuple'] =
  identity.workflowCommit === tuple.commit &&
  Number(identity.runId) === tuple.runId &&
  identity.sourceArchiveSha256 === tuple.sourceArchiveSha256 &&
  identity.workflowSha256 === tuple.generatedPlanSha256 &&
  identity.portableSchemaDialect === 'https://json-schema.org/draft/2020-12/schema' &&
  identity.portableSchemaContractVersion === '1.0.0' &&
  identity.axeIncompleteNodeCount === 498;
checks['builder-package-hash-bound-to-tuple'] =
  shaFile(path.join(builder, 'R7E_PACKAGE_VALIDATION.json')) === tuple.packageValidationSha256;
checks['builder-executor-hash-bound-to-tuple'] =
  shaFile(path.join(builder, 'R7E_SELF_RECORDING_VALIDATION.json')) === tuple.executorValidationSha256;
checks['builder-generated-plan-hash-bound-to-tuple'] =
  shaFile(path.join(builder, 'R7E_EXECUTOR_EVIDENCE/generated-authoritative-plan.yml')) === tuple.generatedPlanSha256;

const mutatedSelf = structuredClone(selfValidation);
mutatedSelf.mainMutationAuthorized = true;
const authenticSelf = (candidate) =>
  candidate?.passed === true &&
  candidate?.mainMutationAuthorized === false &&
  candidate?.productionDeploymentAuthorized === false &&
  Array.isArray(candidate?.failedChecks) &&
  candidate.failedChecks.length === 0 &&
  Object.values(candidate?.checks ?? {}).every((value) => value === true);
checks['negative-mutated-self-recording-rejected'] = authenticSelf(mutatedSelf) === false;

const schemaRows = schemaNames.map((name) => ({
  path: name,
  sha256: shaFile(path.join(verifierSchemaDir, name)),
  size: fs.statSync(path.join(verifierSchemaDir, name)).size,
}));
const schemaTreeSha256 = shaBytes(
  Buffer.from(schemaRows.map((row) => `${row.path}\0${row.sha256}\0${row.size}\n`).join('')),
);
checks['portable-index-hash-bound'] = shaFile(path.join(verifierSchemaDir, 'index.json')) === identity.portableSchemaIndexSha256;

const failedChecks = Object.entries(checks)
  .filter(([, passed]) => passed !== true)
  .map(([name]) => name);
const result = {
  schema: 'R7F_INDEPENDENT_PORTABLE_SELF_RECORDING_AUDIT_V1',
  passed: failedChecks.length === 0,
  checks,
  failedChecks,
  metrics: {
    schemaJsonFileCount: schemaNames.length,
    compiledSchemaCount: Object.keys(validators).length,
    canonicalRecordCount: recordCount,
    axeNodeCount: identity.axeIncompleteNodeCount,
    generatedPlanRunStepCount: execution.executedRunStepCount,
  },
  schemaTreeSha256,
  schemaFiles: schemaRows,
  r7eTuple: tuple,
  tupleArtifact: {
    id: expected.tupleArtifactId,
    name: expected.tupleArtifactName,
    digest: expected.tupleArtifactDigest,
  },
  errors,
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
if (!result.passed) process.exit(1);
