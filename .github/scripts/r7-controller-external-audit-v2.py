#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile


class AuditFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditFailure(message)


def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def load(path: Path): return json.loads(path.read_text(encoding='utf-8'))


def unique(root: Path,name: str) -> Path:
    matches=list(root.rglob(name)); require(len(matches)==1,f'expected one {name}, found {len(matches)}'); return matches[0]


def safe_extract(source: Path,target: Path) -> dict:
    shutil.rmtree(target,ignore_errors=True); target.mkdir(parents=True); seen=set(); files=0
    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            pure=PurePosixPath(info.filename); file_type=stat.S_IFMT(info.external_attr>>16)
            require(not pure.is_absolute() and '..' not in pure.parts,f'unsafe ZIP path: {info.filename}')
            require(info.filename not in seen,f'duplicate ZIP entry: {info.filename}')
            require(file_type!=stat.S_IFLNK,f'ZIP symlink rejected: {info.filename}')
            seen.add(info.filename); files+=0 if info.is_dir() else 1
        archive.extractall(target)
    return {'entryCount':len(seen),'regularFileCount':files}


def verify_manifest(root: Path) -> tuple[Path,int]:
    manifest=unique(root,'R7_CONTROLLER_ARTIFACT_SHA256SUMS.txt'); artifact_root=manifest.parent; rows={}
    for raw in manifest.read_text().splitlines():
        if not raw.strip(): continue
        require('  ' in raw,f'invalid manifest line: {raw!r}')
        digest,relative=raw.split('  ',1); relative=relative.lstrip('*'); pure=PurePosixPath(relative)
        require(len(digest)==64 and all(ch in '0123456789abcdef' for ch in digest),'invalid manifest digest')
        require(not pure.is_absolute() and '..' not in pure.parts and relative not in rows,f'unsafe manifest path: {relative}')
        rows[relative]=digest
    actual={p.relative_to(artifact_root).as_posix() for p in artifact_root.rglob('*') if p.is_file() and p!=manifest}
    require(set(rows)==actual,'controller artifact manifest coverage mismatch')
    for relative,digest in rows.items(): require(sha256_file(artifact_root/relative)==digest,f'controller artifact hash mismatch: {relative}')
    return artifact_root,len(rows)


def regenerate_manifest(root: Path) -> None:
    manifest=root/'R7_CONTROLLER_ARTIFACT_SHA256SUMS.txt'; rows=[]
    for path in sorted((p for p in root.rglob('*') if p.is_file() and p!=manifest),key=lambda p:p.relative_to(root).as_posix().encode()): rows.append(f'{sha256_file(path)}  {path.relative_to(root).as_posix()}')
    manifest.write_text('\n'.join(rows)+'\n')


def semantic(root: Path) -> dict:
    controller_path=unique(root,'R7_HISTORY_BOUND_FINAL_CONTROLLER_V4.json')
    controller_selftest_path=unique(root,'R7_HISTORY_BOUND_CONTROLLER_SELFTEST_V4.json')
    live_path=unique(root,'R7_LIVE_GITHUB_BINDING_V3.json')
    r7e_path=unique(root,'R7E_STATUS.json'); r7f_path=unique(root,'R7F_STATUS.json'); external_path=unique(root,'EXTERNAL_STATUS.json'); trace_status_path=unique(root,'TRACEABILITY_STATUS.json')
    corpus_path=unique(root,'R7_FULL_HISTORY_CORPUS_MANIFEST_V4.json'); traceability_path=unique(root,'R7_REQUIREMENTS_TRACEABILITY_V4.json'); carry_path=unique(root,'R7_CARRY_FORWARD_REGISTER_V4.json'); readiness_path=unique(root,'R7_ZERO_ORPHAN_READINESS_V4.json')
    trace_verification_path=unique(root,'R7_FULL_HISTORY_TRACEABILITY_VERIFICATION_V4.json'); trace_selftest_path=unique(root,'R7_FULL_HISTORY_TRACEABILITY_SELFTEST_V4.json')
    external_report_path=unique(root,'R7_PORTABLE_EXTERNAL_AUDIT_V4.json'); external_selftest_path=unique(root,'R7_PORTABLE_EXTERNAL_AUDIT_SELFTEST_V4.json')
    authority_path=unique(root,'R7_AUTHORITY_HIERARCHY_V3.json'); roadmap_path=unique(root,'DAVID_ANDERLE_WEBSITE_PROGRAMME_ROADMAP_V3.json'); ownership_path=unique(root,'BEARING_OWNERSHIP_DECISION_V3.json')
    workflow_path=unique(root,'r7-history-bound-controller-v4.yml'); gate_path=unique(root,'R7_ENGINEERING_GATE_DECISION.txt')

    controller=load(controller_path); controller_selftest=load(controller_selftest_path); live=load(live_path)
    r7e=load(r7e_path); r7f=load(r7f_path); external=load(external_path); trace_status=load(trace_status_path)
    corpus=load(corpus_path); traceability=load(traceability_path); carry=load(carry_path); readiness=load(readiness_path)
    trace_verification=load(trace_verification_path); trace_selftest=load(trace_selftest_path); external_report=load(external_report_path); external_selftest=load(external_selftest_path)
    authority=load(authority_path); roadmap=load(roadmap_path); ownership=load(ownership_path)
    workflow=workflow_path.read_text(); gate=gate_path.read_text()

    adapter=controller.get('compatibilityAdapter',{})
    transformations=adapter.get('allowedTransformations',[])
    checks={
        'controller-schema':controller.get('schema')=='R7_HISTORY_BOUND_FINAL_CONTROLLER_V4',
        'controller-pass':controller.get('passed') is True and controller.get('decision')=='R7_CLOSED',
        'controller-maximum':controller.get('maximumAuthorizedVerdict')=='R7_TECHNICAL_ARCHITECTURE_CLOSED',
        'controller-all-checks':controller.get('checkCount',0)>85 and controller.get('checkCount')==controller.get('passedCheckCount') and controller.get('failedChecks')==[] and controller.get('blockers')==[],
        'controller-scope':controller.get('scope',{}).get('mainMutationAuthorized') is False and controller.get('scope',{}).get('productionDeploymentAuthorized') is False,
        'controller-r8-r13-open':controller.get('scope',{}).get('notClosed')==['whole website programme','R8 security','R9 discoverability','R10 final authority','R11 clean-room build','R12 release red team','R13 live audit'],
        'controller-ownership-caveat':controller.get('ownershipCaveatPreserved') is True,
        'adapter-pass':adapter.get('passed') is True and adapter.get('digestOrLinkMutationAllowed') is False,
        'adapter-two-schema-labels':len(transformations)==2 and {row.get('field') for row in transformations}=={'r7f.schema','external.schema'},
        'adapter-r7f-digest-unchanged':adapter.get('originalR7fArtifactDigest')==adapter.get('normalizedR7fArtifactDigest')==r7f.get('artifact',{}).get('digest'),
        'adapter-external-digest-unchanged':adapter.get('originalExternalArtifactDigest')==adapter.get('normalizedExternalArtifactDigest')==external.get('artifact',{}).get('digest'),
        'controller-selftest':controller_selftest.get('passed') is True and controller_selftest.get('caseCount')==14 and controller_selftest.get('passedCaseCount')==14 and controller_selftest.get('authenticDecision')=='R7_CLOSED',
        'live-main':live.get('main',{}).get('baselineSha')==live.get('main',{}).get('currentSha')=='bcc55fa7125013615f076dd7cf28a8ec9c5f232b',
        'live-scope':live.get('productionDeploymentAuthorized') is False and live.get('wholeSiteComplete') is False,
        'r7e-status':r7e.get('schema')=='R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3' and r7e.get('passed') is True,
        'r7f-status':r7f.get('schema')=='R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V5' and r7f.get('passed') is True and r7f.get('correctionModel')=='EXACT_FOUR_CLASS_PATH_REPAIR',
        'external-status':external.get('schema')=='R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V4' and external.get('passed') is True and external.get('correctionModel')=='EXACT_FOUR_CLASS_PATH_REPAIR',
        'trace-status':trace_status.get('schema')=='R7_FULL_HISTORY_TRACEABILITY_TUPLE_V4' and trace_status.get('passed') is True,
        'r7f-r7e-link':r7f.get('builder',{}).get('commit')==r7e.get('commit') and r7f.get('builder',{}).get('artifactDigest')==r7e.get('artifact',{}).get('digest'),
        'external-r7f-link':external.get('r7f',{}).get('commit')==r7f.get('commit') and external.get('r7f',{}).get('artifactDigest')==r7f.get('artifact',{}).get('digest'),
        'external-r7e-link':external.get('r7e',{}).get('commit')==r7e.get('commit') and external.get('r7e',{}).get('artifactDigest')==r7e.get('artifact',{}).get('digest'),
        'trace-corpus-hash':trace_status.get('hashes',{}).get('corpus')==sha256_file(corpus_path),
        'trace-requirements-hash':trace_status.get('hashes',{}).get('traceability')==sha256_file(traceability_path),
        'trace-carry-hash':trace_status.get('hashes',{}).get('carryForward')==sha256_file(carry_path),
        'trace-readiness-hash':trace_status.get('hashes',{}).get('readiness')==sha256_file(readiness_path),
        'trace-verification-hash':trace_status.get('hashes',{}).get('verification')==sha256_file(trace_verification_path),
        'trace-selftest-hash':trace_status.get('hashes',{}).get('selftest')==sha256_file(trace_selftest_path),
        'zero-orphan':readiness.get('passed') is True and readiness.get('openR7BlockerCount')==0 and readiness.get('orphanedRequirementCount')==0 and readiness.get('unresolvedMaterialClauseCount')==0,
        'trace-verification':trace_verification.get('passed') is True and trace_verification.get('decision')=='ZERO_ORPHAN_TRACEABILITY_VERIFIED',
        'trace-selftest':trace_selftest.get('passed') is True and trace_selftest.get('caseCount')==10 and trace_selftest.get('passedCaseCount')==10,
        'external-report-hash':external.get('auditSha256')==sha256_file(external_report_path),
        'external-selftest-hash':external.get('selftestSha256')==sha256_file(external_selftest_path),
        'external-report':external_report.get('passed') is True and external_report.get('decision')=='R7_PORTABLE_EXTERNAL_AUDIT_PASS' and external_report.get('metrics',{}).get('pathCorrectionClasses')==4,
        'external-selftest':external_selftest.get('passed') is True and external_selftest.get('caseCount')==7 and external_selftest.get('passedCaseCount')==7,
        'authority':authority.get('designIdentity')=='BEARING' and authority.get('designFrozen') is True,
        'roadmap':next((row.get('status') for row in roadmap.get('phases',[]) if row.get('id')=='R7'),None)=='CLOSURE_CANDIDATE' and all(next((row.get('status') for row in roadmap.get('phases',[]) if row.get('id')==f'R{number}'),None)=='NOT_STARTED' for number in range(8,14)),
        'ownership':ownership.get('substantiveApproval')=='USER_DELEGATED_SUBSTANTIVE_APPROVAL' and ownership.get('formalQuantitativeBlindProtocolRecorded') is False and ownership.get('requiredFutureGates')==['R10','R12'],
        'traceability-scope':traceability.get('requestedClosureClaims')==['R7_TECHNICAL_ARCHITECTURE_CLOSED'],
        'traceability-zero-lists':traceability.get('orphanedRequirementIds')==[] and traceability.get('contradictions')==[] and traceability.get('unexplainedDeviations')==[],
        'carry-zero-unbound':carry.get('unboundEntries')==[],
        'workflow-read-only':'permissions:\n  contents: read\n  actions: read' in workflow,
        'workflow-no-write':'contents: write' not in workflow and 'actions: write' not in workflow and 'git push' not in workflow,
        'workflow-no-deploy':'wrangler deploy' not in workflow and 'cloudflare deploy' not in workflow.lower(),
        'gate-exact':gate=='R7_CLOSED — TECHNICAL ARCHITECTURE AND EMPIRICAL VERIFICATION ONLY\nR8–R13 REMAIN OPEN\nMAIN MUTATION NOT AUTHORIZED\nPRODUCTION DEPLOYMENT NOT AUTHORIZED\nWHOLE WEBSITE PROGRAMME NOT COMPLETE\n',
    }
    input_map={'r7e':r7e_path,'r7f':r7f_path,'external':external_path,'traceability':traceability_path,'carry':carry_path,'authority':authority_path,'roadmap':roadmap_path,'ownership':ownership_path,'live':live_path}
    checks['controller-input-hashes']=controller.get('inputSha256')=={key:sha256_file(path) for key,path in input_map.items()}
    checks['evidence-r7e']=controller.get('evidenceChain',{}).get('r7e')=={'commit':r7e.get('commit'),'runId':r7e.get('runId'),'artifact':r7e.get('artifact')}
    checks['evidence-r7f']=controller.get('evidenceChain',{}).get('r7f')=={'commit':r7f.get('commit'),'runId':r7f.get('runId'),'artifact':r7f.get('artifact')}
    checks['evidence-external']=controller.get('evidenceChain',{}).get('external')=={'commit':external.get('commit'),'runId':external.get('runId'),'artifact':external.get('artifact')}
    failed=sorted(name for name,passed in checks.items() if not passed)
    require(not failed,f'controller v4 external audit failed: {failed}')
    return {'checks':checks,'failedChecks':[],'metrics':{'controllerCheckCount':controller.get('checkCount'),'controllerSelftestCases':controller_selftest.get('caseCount'),'traceabilityRequirementCount':traceability.get('summary',{}).get('requirementCount'),'carryForwardCount':len(carry.get('entries',[])),'traceabilitySelftestCases':trace_selftest.get('caseCount'),'portableExternalSelftestCases':external_selftest.get('caseCount'),'pathCorrectionClasses':external_report.get('metrics',{}).get('pathCorrectionClasses')}}


def selftests(root: Path) -> dict:
    cases=[]
    def run_case(name,filename,mutate):
        with tempfile.TemporaryDirectory(prefix=f'r7-controller-v2-{name}-') as temp:
            target=Path(temp)/'artifact'; shutil.copytree(root,target); path=unique(target,filename)
            if path.suffix=='.json':
                data=load(path); mutate(data); path.write_text(json.dumps(data,indent=2)+'\n')
            else: path.write_text(mutate(path.read_text()))
            regenerate_manifest(target); rejected=False; error=None
            try: semantic(target)
            except AuditFailure as exc: rejected=True; error=str(exc)
            cases.append({'name':name,'rejected':rejected,'error':error})
    run_case('decision','R7_HISTORY_BOUND_FINAL_CONTROLLER_V4.json',lambda d:d.__setitem__('decision','WHOLE_SITE_COMPLETE'))
    run_case('adapter','R7_HISTORY_BOUND_FINAL_CONTROLLER_V4.json',lambda d:d['compatibilityAdapter'].__setitem__('digestOrLinkMutationAllowed',True))
    run_case('controller-selftest','R7_HISTORY_BOUND_CONTROLLER_SELFTEST_V4.json',lambda d:d.__setitem__('passedCaseCount',13))
    run_case('main','R7_LIVE_GITHUB_BINDING_V3.json',lambda d:d['main'].__setitem__('currentSha','0'*40))
    run_case('orphan','R7_REQUIREMENTS_TRACEABILITY_V4.json',lambda d:d.__setitem__('orphanedRequirementIds',['INJECTED']))
    run_case('external','R7_PORTABLE_EXTERNAL_AUDIT_V4.json',lambda d:d.__setitem__('passed',False))
    run_case('ownership','BEARING_OWNERSHIP_DECISION_V3.json',lambda d:d.__setitem__('formalQuantitativeBlindProtocolRecorded',True))
    run_case('r7f-model','R7F_STATUS.json',lambda d:d.__setitem__('correctionModel','FAKE'))
    run_case('r7f-link','R7F_STATUS.json',lambda d:d['builder'].__setitem__('artifactDigest','sha256:'+'0'*64))
    run_case('permissions','r7-history-bound-controller-v4.yml',lambda text:text.replace('contents: read','contents: write',1))
    passed=len(cases)==10 and all(row['rejected'] for row in cases); require(passed,f'controller v2 auditor self-tests failed: {cases}')
    return {'schema':'R7_CONTROLLER_EXTERNAL_AUDIT_SELFTEST_V2','passed':True,'caseCount':10,'passedCaseCount':10,'cases':cases}


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('--zip',required=True,dest='zip_path'); parser.add_argument('--run',required=True,dest='run_path'); parser.add_argument('--artifact',required=True,dest='artifact_path'); parser.add_argument('--expected-commit',required=True); parser.add_argument('--expected-branch',required=True); parser.add_argument('--output',required=True); parser.add_argument('--selftest-output',required=True); args=parser.parse_args()
    zip_path=Path(args.zip_path).resolve(); run=load(Path(args.run_path).resolve()); artifact=load(Path(args.artifact_path).resolve())
    require(run.get('status')=='completed' and run.get('conclusion')=='success','controller v4 run not successful'); require(run.get('head_sha')==args.expected_commit and run.get('head_branch')==args.expected_branch,'controller v4 run identity mismatch'); require(artifact.get('workflow_run',{}).get('id')==run.get('id') and artifact.get('expired') is False,'controller v4 artifact metadata mismatch')
    digest=artifact.get('digest',''); require(digest.startswith('sha256:') and sha256_file(zip_path)==digest.removeprefix('sha256:'),'controller v4 outer digest mismatch')
    with tempfile.TemporaryDirectory(prefix='r7-controller-v2-') as temp:
        extracted=Path(temp)/'extracted'; zip_metrics=safe_extract(zip_path,extracted); artifact_root,manifest_entries=verify_manifest(extracted); audited=semantic(artifact_root); tests=selftests(artifact_root)
    report={'schema':'R7_CONTROLLER_EXTERNAL_AUDIT_V2','passed':True,'decision':'R7_FINAL_ENGINEERING_CLOSURE_VERIFIED','controller':{'commit':args.expected_commit,'branch':args.expected_branch,'runId':run.get('id'),'artifactId':artifact.get('id'),'artifactName':artifact.get('name'),'artifactDigest':artifact.get('digest'),'downloadedZipSha256':sha256_file(zip_path)},'zip':zip_metrics,'manifestEntryCount':manifest_entries,**audited,'selftest':{'passed':True,'caseCount':10},'maximumAuthorizedVerdict':'R7_TECHNICAL_ARCHITECTURE_CLOSED','notAuthorized':['whole-site completion','production deployment','main mutation','R8-R13 closure']}
    output=Path(args.output).resolve(); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2)+'\n'); Path(args.selftest_output).resolve().write_text(json.dumps(tests,indent=2)+'\n'); print(json.dumps(report,indent=2))


if __name__=='__main__':
    try: main()
    except AuditFailure as exc: raise SystemExit(str(exc))
