import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [builderArg, verifierArg, tupleArg, outputArg] = process.argv.slice(2);
if (!builderArg || !verifierArg || !tupleArg || !outputArg) {
  throw new Error('Usage: auditor BUILDER_ROOT VERIFIER_ROOT TUPLE_JSON OUTPUT_JSON');
}

const builder = path.resolve(builderArg);
const verifier = path.resolve(verifierArg);
const tuplePath = path.resolve(tupleArg);
const output = path.resolve(outputArg);
const bSource = path.join(builder, 'BEARING_PRODUCTION_SOURCE');
const bEvidence = path.join(builder, 'R7E_EVIDENCE');

const read = (p) => fs.readFileSync(p);
const readText = (p) => fs.readFileSync(p, 'utf8');
const readJson = (p) => JSON.parse(readText(p));
const sha = (value) => crypto.createHash('sha256').update(value).digest('hex');
const deepSort = (value) => Array.isArray(value)
  ? value.map(deepSort)
  : (value && typeof value === 'object')
    ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, deepSort(value[key])]))
    : value;
const canonical = (value) => `${JSON.stringify(deepSort(value), null, 2)}\n`;
const canonicalCompact = (value) => JSON.stringify(deepSort(value));
const equalJson = (a, b) => canonicalCompact(a) === canonicalCompact(b);

const checks = {};
const errors = [];
const check = (name, value) => { checks[name] = Boolean(value); };

const tuple = readJson(tuplePath);
const identity = readJson(path.join(bEvidence, 'R7E_CANDIDATE_IDENTITY.json'));
const packageValidation = readJson(path.join(builder, 'R7E_PACKAGE_VALIDATION.json'));
const execution = readJson(path.join(bEvidence, 'generated-plan-execution-v2.json'));
const planPath = path.join(bEvidence, 'generated-authoritative-plan.yml');
const planText = readText(planPath);
const mainManifestPath = path.join(builder, 'R7E_ARTIFACT_SHA256SUMS.txt');
const executorInfrastructurePath = path.join(bEvidence, 'executor-v4-infrastructure.sha256');

const expectedSteps = [
  'Record runner environment',
  'Materialize immutable canonical source',
  'Verify exact toolchain and complete lockfile',
  'Verify portable Draft 2020-12 schema contract',
  'Freeze source and deterministic transport',
  'Clean Run 1',
  'Clean Run 2',
  'Reproducibility gate',
  'Invalid fixture gate',
  '500-record native Astro lineage gate',
  'Install Chromium for browser gates',
  'Browser matrix and no-JavaScript gates',
  'Axe accessibility and dynamic exact fingerprint adjudication',
  'Lighthouse measurements',
  'Runtime network audit',
  'Wrangler assets-only dry run',
  'Final immutability and candidate identity gate',
  'Assemble successful evidence artifact',
];

check('tuple-schema-v4', tuple.schema === 'R7E_PORTABLE_SELF_RECORDING_AUTHORITATIVE_TUPLE_V4');
check('tuple-passed', tuple.passed === true && tuple.branchHeadUnchanged === true);
check('tuple-repository', tuple.repository === process.env.GITHUB_REPOSITORY);
check('tuple-branch', tuple.branch === process.env.BUILDER_BRANCH);
check('tuple-workflow-path', tuple.workflowPath === process.env.BUILDER_WORKFLOW_PATH);
check('tuple-commit', tuple.commit === process.env.BUILDER_COMMIT);
check('tuple-run', String(tuple.runId) === process.env.BUILDER_RUN_ID);
check('tuple-main-artifact',
  String(tuple.artifact?.id) === process.env.BUILDER_ARTIFACT_ID &&
  tuple.artifact?.name === process.env.BUILDER_ARTIFACT_NAME &&
  tuple.artifact?.digest === process.env.BUILDER_ARTIFACT_DIGEST
);
check('tuple-source-archive', tuple.sourceArchiveSha256 === process.env.BUILDER_SOURCE_ARCHIVE_SHA256);
check('tuple-source-file-count', tuple.sourceFileCount === 146);
check('tuple-plan-hash',
  tuple.generatedPlan?.sha256 === process.env.BUILDER_GENERATED_PLAN_SHA256 &&
  tuple.generatedPlan?.sha256 === sha(read(planPath))
);
check('tuple-generator-hash', tuple.generatedPlan?.generatorSha256 === process.env.BUILDER_GENERATOR_SHA256);
check('tuple-executor-hash', tuple.generatedPlan?.executorSha256 === process.env.BUILDER_EXECUTOR_SHA256);
check('tuple-execution-contract',
  tuple.generatedPlan?.executionSchema === 'R7E_GENERATED_PLAN_EXECUTION_V2' &&
  tuple.generatedPlan?.executedRunStepCount === 18
);
check('tuple-package-validation-hash',
  tuple.evidence?.packageValidationSha256 === sha(read(path.join(builder, 'R7E_PACKAGE_VALIDATION.json')))
);
check('tuple-main-manifest-hash',
  tuple.evidence?.internalManifestSha256 === sha(read(mainManifestPath))
);
check('tuple-executor-infrastructure-hash',
  tuple.evidence?.executorInfrastructureSha256 === sha(read(executorInfrastructurePath))
);
check('tuple-candidate-identity-exact', equalJson(tuple.candidateIdentity, identity));
check('tuple-scope-bounded',
  String(tuple.scope).includes('no main mutation') &&
  String(tuple.scope).includes('no R8-R13 closure') &&
  String(tuple.scope).includes('no production release authorization')
);

check('identity-schema', identity.schema === 'R7E_PORTABLE_JSON_SCHEMA_CANDIDATE_IDENTITY_V1');
check('identity-run-commit',
  identity.repository === process.env.GITHUB_REPOSITORY &&
  identity.workflowCommit === process.env.BUILDER_COMMIT &&
  String(identity.runId) === process.env.BUILDER_RUN_ID
);
check('identity-source-archive', identity.sourceArchiveSha256 === process.env.BUILDER_SOURCE_ARCHIVE_SHA256);
check('identity-source-tree', identity.frozenSourceTreeSha256 === process.env.BUILDER_FROZEN_SOURCE_TREE_SHA256);
check('identity-source-tar', identity.frozenSourceTarSha256 === process.env.BUILDER_FROZEN_SOURCE_TAR_SHA256);
check('identity-dist-tree', identity.verifiedDistTreeSha256 === process.env.BUILDER_VERIFIED_DIST_TREE_SHA256);
check('identity-stress-tree', identity.stressDistTreeSha256 === process.env.BUILDER_STRESS_DIST_TREE_SHA256);
check('identity-axe-file', identity.axeAdjudicationFileSha256 === process.env.BUILDER_AXE_ADJUDICATION_FILE_SHA256);
check('identity-axe-semantic', identity.axeSemanticInventorySha256 === process.env.BUILDER_AXE_SEMANTIC_INVENTORY_SHA256);
check('identity-axe-node-set', identity.axeNodeFingerprintSetSha256 === process.env.BUILDER_AXE_NODE_SET_SHA256);
check('identity-axe-binding-set', identity.axeBindingFingerprintSetSha256 === process.env.BUILDER_AXE_BINDING_SET_SHA256);
check('identity-axe-count', String(identity.axeIncompleteNodeCount) === process.env.BUILDER_AXE_INCOMPLETE_NODE_COUNT);
check('identity-portable-contract',
  identity.portableSchemaContractVersion === '1.0.0' &&
  identity.portableSchemaDialect === 'https://json-schema.org/draft/2020-12/schema'
);
check('package-validation', packageValidation.passed === true && (packageValidation.failedChecks ?? []).length === 0);

check('execution-schema', execution.schema === 'R7E_GENERATED_PLAN_EXECUTION_V2');
check('execution-passed', execution.passed === true && execution.firstFailure === null);
check('execution-step-count', execution.executedRunStepCount === 18);
check('execution-step-names', equalJson((execution.steps ?? []).map((row) => row.name), expectedSteps));
check('execution-zero-exits', (execution.steps ?? []).every((row) => row.exitCode === 0));
check('execution-skipped-uses',
  execution.skippedAllowedUsesCount === 3 &&
  equalJson((execution.skippedAllowedUses ?? []).map((row) => row.uses), [
    'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
    'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020',
    'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
  ])
);
check('execution-condition-semantics',
  execution.skippedConditionCount === 1 &&
  execution.skippedConditions?.[0]?.name === 'Assemble diagnostic artifact on failure' &&
  execution.skippedConditions?.[0]?.condition === 'failure'
);
check('execution-plan-hash', execution.workflowSha256 === sha(read(planPath)));
check('plan-current-script-names',
  planText.includes('scripts/validate-json-schemas.mjs') &&
  planText.includes('scripts/run-portable-schema-contract.mjs') &&
  !planText.includes('scripts/validate-json-schema.mjs') &&
  !planText.includes('scripts/verify-json-schema-drift.mjs')
);
check('plan-standard-dialect-field',
  planText.includes('."$schema"=="https://json-schema.org/draft/2020-12/schema"')
);

const req = createRequire(path.join(verifier, 'package.json'));
const AjvModule = req('ajv/dist/2020.js');
const Ajv2020 = AjvModule.default ?? AjvModule;
const zodModule = req('zod');
const z = zodModule.z ?? zodModule;
const schemaModule = await import(`${pathToFileURL(path.join(verifier, 'src/content-schemas.ts')).href}?r7f=${Date.now()}`);
const parserModule = await import(pathToFileURL(path.join(verifier, 'scripts/lib/frontmatter.mjs')).href);
const {
  portableSchemas,
  portableSchemaMetadata,
  PORTABLE_SCHEMA_VERSION,
  JSON_SCHEMA_DIALECT,
} = schemaModule;

const generated = {};
for (const [name, schema] of Object.entries(portableSchemas)) {
  const metadata = portableSchemaMetadata[name];
  const converted = z.toJSONSchema(schema, {
    target: 'draft-2020-12',
    io: 'input',
    unrepresentable: 'throw',
  });
  delete converted.id;
  generated[metadata.file] = {
    $schema: JSON_SCHEMA_DIALECT,
    $id: metadata.id,
    title: metadata.title,
    'x-contract-version': PORTABLE_SCHEMA_VERSION,
    'x-source': 'src/content-schemas.ts',
    ...converted,
  };
}
generated['index.json'] = {
  $schema: JSON_SCHEMA_DIALECT,
  $id: 'https://davidanderle.com/schemas/index.json',
  title: 'David Anderle portable public content contracts',
  contractVersion: PORTABLE_SCHEMA_VERSION,
  source: 'src/content-schemas.ts',
  schemas: Object.entries(portableSchemaMetadata).map(([name, metadata]) => ({
    name,
    file: metadata.file,
    $id: metadata.id,
  })),
};

const expectedFiles = Object.keys(generated).sort();
const builderSchemaRoot = path.join(bSource, 'schemas');
const verifierSchemaRoot = path.join(verifier, 'schemas');
const builderFiles = fs.readdirSync(builderSchemaRoot).filter((name) => name.endsWith('.json')).sort();
const verifierFiles = fs.readdirSync(verifierSchemaRoot).filter((name) => name.endsWith('.json')).sort();
check('portable-schema-file-set-builder', equalJson(builderFiles, expectedFiles));
check('portable-schema-file-set-verifier', equalJson(verifierFiles, expectedFiles));
check('portable-schema-file-set-parity', equalJson(builderFiles, verifierFiles));

let generatedParity = true;
let builderVerifierParity = true;
for (const file of expectedFiles) {
  const expectedBytes = canonical(generated[file]);
  const builderBytes = readText(path.join(builderSchemaRoot, file));
  const verifierBytes = readText(path.join(verifierSchemaRoot, file));
  if (builderBytes !== expectedBytes || verifierBytes !== expectedBytes) generatedParity = false;
  if (builderBytes !== verifierBytes) builderVerifierParity = false;
}
check('portable-schema-generated-byte-parity', generatedParity);
check('portable-schema-builder-verifier-byte-parity', builderVerifierParity);
check('portable-schema-dialect', JSON_SCHEMA_DIALECT === 'https://json-schema.org/draft/2020-12/schema');
check('portable-schema-version', PORTABLE_SCHEMA_VERSION === '1.0.0');

const ajv = new Ajv2020({ allErrors: true, strict: true, validateFormats: false });
ajv.addKeyword({ keyword: 'x-contract-version', schemaType: 'string', valid: true });
ajv.addKeyword({ keyword: 'x-source', schemaType: 'string', valid: true });
const validators = {};
for (const [file, schema] of Object.entries(generated)) {
  if (file !== 'index.json') validators[file] = ajv.compile(schema);
}
check('portable-eight-schemas-compiled', Object.keys(validators).length === 8);

const list = (directory, suffix) => fs.readdirSync(directory, { recursive: true })
  .filter((entry) => typeof entry === 'string' && entry.endsWith(suffix))
  .sort()
  .map((entry) => path.join(directory, entry));
const parseMarkdown = (file) => parserModule.parseMarkdownFile(file).data;
const contentRoot = path.join(verifier, 'src/content');
const groups = {
  profile: list(path.join(contentRoot, 'profile'), '.json').map((file) => readJson(file)),
  work: list(path.join(contentRoot, 'work'), '.md').map(parseMarkdown),
  writing: list(path.join(contentRoot, 'writing'), '.md').map(parseMarkdown),
  milestones: readJson(path.join(contentRoot, 'milestones.json')),
  publicDocuments: readJson(path.join(contentRoot, 'public-documents.json')),
  redirects: readJson(path.join(contentRoot, 'redirects.json')),
  tombstones: readJson(path.join(contentRoot, 'tombstones.json')),
};
const mapping = {
  profile: ['profile.schema.json', portableSchemas.profile],
  work: ['work-record.schema.json', portableSchemas.work],
  writing: ['writing-record.schema.json', portableSchemas.writing],
  milestones: ['milestone.schema.json', portableSchemas.milestone],
  publicDocuments: ['public-document.schema.json', portableSchemas.publicDocument],
  redirects: ['redirect-record.schema.json', portableSchemas.redirect],
  tombstones: ['tombstone-record.schema.json', portableSchemas.tombstone],
};

let recordCount = 0;
let parityProbeCount = 0;
const validationErrors = [];
for (const [group, rows] of Object.entries(groups)) {
  const [schemaFile, zodSchema] = mapping[group];
  const validator = validators[schemaFile];
  const schema = generated[schemaFile];
  for (const [index, row] of rows.entries()) {
    recordCount += 1;
    const ajvPassed = Boolean(validator(row));
    const zodResult = zodSchema.safeParse(row);
    if (!ajvPassed || !zodResult.success || ajvPassed !== zodResult.success) {
      validationErrors.push({ group, index, ajvErrors: validator.errors ?? [], zodErrors: zodResult.success ? [] : zodResult.error.issues });
    }
    const unknown = { ...structuredClone(row), __r7fUnknown: true };
    parityProbeCount += 1;
    if (validator(unknown) !== false || zodSchema.safeParse(unknown).success !== false) {
      validationErrors.push({ group, index, probe: 'unknown-property' });
    }
    const required = (schema.required ?? [])[0];
    if (required) {
      const missing = structuredClone(row);
      delete missing[required];
      parityProbeCount += 1;
      if (validator(missing) !== false || zodSchema.safeParse(missing).success !== false) {
        validationErrors.push({ group, index, probe: `missing:${required}` });
      }
    }
  }
}
const corpus = { schemaVersion: PORTABLE_SCHEMA_VERSION, ...groups };
const corpusValidator = validators['canonical-content.schema.json'];
const corpusZod = portableSchemas.corpus.safeParse(corpus);
if (!corpusValidator(corpus) || !corpusZod.success) {
  validationErrors.push({ probe: 'canonical-corpus', ajvErrors: corpusValidator.errors ?? [], zodErrors: corpusZod.success ? [] : corpusZod.error.issues });
}
check('portable-twelve-records', recordCount === 12);
check('portable-dual-engine-record-validation', validationErrors.length === 0);

const invalid = structuredClone(groups.profile[0]);
delete invalid.immutableId;
const invalidRejected = validators['profile.schema.json'](invalid) === false
  && portableSchemas.profile.safeParse(invalid).success === false;
const stale = structuredClone(generated['profile.schema.json']);
stale.title = 'R7F DELIBERATE STALE MUTATION';
const staleRejected = canonical(stale) !== readText(path.join(builderSchemaRoot, 'profile.schema.json'));
check('portable-invalid-record-negative-rejected', invalidRejected);
check('portable-stale-schema-negative-rejected', staleRejected);

const schemaRows = expectedFiles.map((file) => ({
  file,
  builderSha256: sha(read(path.join(builderSchemaRoot, file))),
  verifierSha256: sha(read(path.join(verifierSchemaRoot, file))),
}));
const schemaTreeSha256 = sha(Buffer.from(schemaRows.map((row) => `${row.file}\0${row.builderSha256}\0${row.verifierSha256}\n`).join('')));
const failedChecks = Object.entries(checks).filter(([, passed]) => !passed).map(([name]) => name);
const result = {
  schema: 'R7F_INDEPENDENT_PORTABLE_SELF_RECORDING_AUDIT_V2',
  passed: failedChecks.length === 0,
  builder,
  verifier,
  tuplePath,
  checks,
  failedChecks,
  metrics: {
    checkCount: Object.keys(checks).length,
    passedCheckCount: Object.values(checks).filter(Boolean).length,
    schemaFileCount: builderFiles.length,
    compiledSchemaCount: Object.keys(validators).length,
    recordCount,
    parityProbeCount,
    executionStepCount: execution.executedRunStepCount,
  },
  schemaTreeSha256,
  schemaRows,
  validationErrors,
  errors,
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify({ passed: result.passed, failedChecks, metrics: result.metrics, schemaTreeSha256 }, null, 2));
if (!result.passed) process.exit(1);
