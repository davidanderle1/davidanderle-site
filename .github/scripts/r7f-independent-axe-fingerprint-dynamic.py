#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_REPORTS = [
    'about-1280.json','about-390.json','archive-1280.json','archive-390.json',
    'home-1280.json','home-390.json','work-1280.json','work-390.json',
    'work-volatility-cascade-engine-1280.json','work-volatility-cascade-engine-390.json',
]
ALLOWED_KEYS={'bgGradient','elmPartiallyObscuring','pseudoContent'}
EXPECTED_BACKGROUND='rgb(7, 16, 20)'

def load(p:Path)->Any: return json.loads(p.read_text(encoding='utf-8'))
def canon(v:Any)->str: return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def vsha(v:Any)->str: return hashlib.sha256(canon(v).encode()).hexdigest()
def fsha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def strarr(v:Any): return list(v) if isinstance(v,list) and all(isinstance(x,str) for x in v) else None
def normalized(v:Any)->Any:
 if not isinstance(v,dict): return v
 x=dict(v); x.pop('timestamp',None); return x
def semantic_summaries(v:Any)->Any:
 if not isinstance(v,list): return v
 return [{k:x for k,x in row.items() if k!='rawSha256'} if isinstance(row,dict) else row for row in v]

def canonical_node(report:str,ri:int,result:dict[str,Any],ni:int,node:dict[str,Any])->dict[str,Any]:
 any_rows=node.get('any') if isinstance(node.get('any'),list) else []
 check=any_rows[0] if len(any_rows)==1 and isinstance(any_rows[0],dict) else {}
 related=check.get('relatedNodes') if isinstance(check.get('relatedNodes'),list) else []
 data=check.get('data') if isinstance(check.get('data'),dict) else {}
 return {
  'schema':'R7_AXE_NODE_FINGERPRINT_V1','report':report,'resultIndex':ri,
  'resultId':result.get('id') if isinstance(result.get('id'),str) else None,
  'nodeIndex':ni,'target':strarr(node.get('target')),
  'html':node.get('html') if isinstance(node.get('html'),str) else None,
  'checkId':check.get('id') if isinstance(check.get('id'),str) else None,
  'impact':check.get('impact') if isinstance(check.get('impact'),str) else None,
  'messageKey':data.get('messageKey') if isinstance(data.get('messageKey'),str) else None,
  'relatedNodes':[{'target':strarr(r.get('target')) if isinstance(r,dict) else None,'html':r.get('html') if isinstance(r,dict) and isinstance(r.get('html'),str) else None} for r in related],
 }

def valid_contrast(p:dict[str,Any])->bool:
 return p.get('designation')=='R7E_STATIC_CONTRAST_BOUND_V1' and p.get('passed') is True and p.get('checkCount')==32 and float(p.get('minimumObservedRatio') or 0)>=4.5 and p.get('failed')==[]
def valid_backplate(p:dict[str,Any],width:int)->bool:
 elements=p.get('elements') if isinstance(p.get('elements'),list) else []
 layers=p.get('layers') if isinstance(p.get('layers'),dict) else {}
 li=p.get('list') if isinstance(p.get('list'),dict) else {}
 targets=[canon(e.get('target')) for e in elements if isinstance(e,dict)]
 common=(p.get('designation')=='R7E_BEARING_ROUTE_BACKPLATE_V2' and p.get('passed') is True and p.get('width')==width and p.get('expectedBackground')==EXPECTED_BACKGROUND and p.get('expectedElementCount')==12 and li.get('tagName')=='OL' and li.get('className')=='bearing-list' and li.get('target')==['ol'] and li.get('openingHtml')=='<ol class="bearing-list">' and len(elements)==12 and len(set(targets))==12 and all(isinstance(e,dict) and e.get('kind') in {'stop-index','time','heading','paragraph'} and isinstance(e.get('target'),list) and len(e['target'])==1 and all(isinstance(x,str) for x in e['target']) and isinstance(e.get('ownerTarget'),list) and len(e['ownerTarget'])==1 and all(isinstance(x,str) for x in e['ownerTarget']) and isinstance(e.get('ownerHtml'),str) and e['ownerHtml'].startswith('<li>') and isinstance(e.get('html'),str) and e['html'] and e.get('backgroundColor')==EXPECTED_BACKGROUND and e.get('backgroundImage')=='none' and e.get('position')=='relative' and e.get('zIndex')=='2' and e.get('passed') is True for e in elements))
 if not common: return False
 return (layers.get('desktopSignatureBelowList') is True and layers.get('mobilePseudoBelowBackplates') is False) if width==1280 else (layers.get('mobilePseudoBelowBackplates') is True and layers.get('desktopSignatureBelowList') is False)

def classify(c:dict[str,Any],contrast_ok:bool,contrast_sha:str|None,proofs:dict[int,dict[str,Any]],proof_shas:dict[int,str|None]):
 errors=[]; target=c.get('target'); html=c.get('html'); key=c.get('messageKey'); related=c.get('relatedNodes') if isinstance(c.get('relatedNodes'),list) else []
 if not isinstance(target,list) or not target: errors.append('TARGET_SHAPE')
 if not isinstance(html,str) or not html: errors.append('HTML_SHAPE')
 if c.get('resultId')!='color-contrast': errors.append('RESULT_ID')
 if c.get('checkId')!='color-contrast': errors.append('CHECK_ID')
 if c.get('impact')!='serious': errors.append('IMPACT')
 if key not in ALLOWED_KEYS: errors.append('MESSAGE_KEY')
 if key=='bgGradient':
  exact=len(related)==1 and (related[0]=={'target':['body'],'html':'<body>'} or related[0]=={'target':['#limitations'],'html':'<section class="limitation-block" id="limitations" aria-labelledby="limitations-title">'})
  if not contrast_ok: errors.append('CONTRAST_PROOF')
  if not exact: errors.append('GRADIENT_RELATED_IDENTITY')
  return 'STATIC_GRADIENT_BOUND',{'proof':'contrast-bounds.json','proofSha256':contrast_sha},not errors,errors
 report=str(c.get('report') or ''); width=1280 if report.endswith('-1280.json') else 390 if report.endswith('-390.json') else 0
 proof=proofs.get(width) or {}; pvalid=valid_backplate(proof,width) if width in (1280,390) else False
 if not pvalid: errors.append('BACKPLATE_PROOF')
 elements=proof.get('elements') if isinstance(proof.get('elements'),list) else []
 exact=[e for e in elements if isinstance(e,dict) and e.get('passed') is True and e.get('target')==target and e.get('html')==html]
 element=exact[0] if len(exact)==1 else None
 if element is None: errors.append('ROUTE_TARGET_NOT_BOUND')
 layers=proof.get('layers') if isinstance(proof.get('layers'),dict) else {}
 if key=='elmPartiallyObscuring':
  if report!='home-1280.json': errors.append('DESKTOP_REPORT')
  if element is None or element.get('kind')!='paragraph': errors.append('DESKTOP_ELEMENT_KIND')
  if related: errors.append('DESKTOP_RELATED_NODES')
  if layers.get('desktopSignatureBelowList') is not True: errors.append('DESKTOP_LAYERING')
  binding={'proof':'axe-compensation/home-route-backplates-1280.json','proofSha256':proof_shas.get(1280),'elementTarget':element.get('target') if element else None,'elementKind':element.get('kind') if element else None}
  return 'OPAQUE_BACKPLATE_DESKTOP_AXIS',binding,not errors,errors
 if key=='pseudoContent':
  if report!='home-390.json': errors.append('MOBILE_REPORT')
  if layers.get('mobilePseudoBelowBackplates') is not True: errors.append('MOBILE_LAYERING')
  if len(related)!=1: errors.append('MOBILE_RELATED_COUNT')
  ident=related[0] if len(related)==1 else None; kind=element.get('kind') if element else None
  if kind=='stop-index': expected={'target':element.get('ownerTarget'),'html':element.get('ownerHtml')}; errors += ([] if ident==expected else ['RELATED_OWNER_MISMATCH'])
  elif kind=='time':
   li=proof.get('list') if isinstance(proof.get('list'),dict) else {}; expected={'target':li.get('target'),'html':li.get('openingHtml')}; errors += ([] if ident==expected else ['RELATED_LIST_MISMATCH'])
  else: errors.append('MOBILE_ELEMENT_KIND')
  binding={'proof':'axe-compensation/home-route-backplates-390.json','proofSha256':proof_shas.get(390),'elementTarget':element.get('target') if element else None,'elementKind':kind,'relatedIdentity':related}
  return 'OPAQUE_BACKPLATE_MOBILE_PSEUDO',binding,not errors,errors
 return 'UNCLASSIFIED',None,False,[*errors,'UNCLASSIFIED']

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('tmp_root',type=Path); ap.add_argument('builder_inventory',type=Path); ap.add_argument('output',type=Path); ap.add_argument('--label',default='candidate'); ap.add_argument('--reference-tmp-root',type=Path,default=None); a=ap.parse_args()
 tmp=a.tmp_root.resolve(); ref=a.reference_tmp_root.resolve() if a.reference_tmp_root else None; bp=a.builder_inventory.resolve(); b=load(bp); checks={}; findings=[]
 def ck(n,v): checks[n]=bool(v)
 be=b.get('entries') if isinstance(b.get('entries'),list) else []; n_expected=len(be)
 ck('builder-present',bp.is_file()); ck('builder-schema',b.get('schema')=='R7E_AXE_FINGERPRINT_ADJUDICATION_V1'); ck('builder-passed',b.get('passed') is True and b.get('failedChecks')==[] and b.get('errors')==[]); ck('builder-nonzero-entry-count',n_expected>0)
 ck('builder-algorithm',(b.get('fingerprintAlgorithm') or {}).get('name')=='sha256-canonical-json')
 ck('builder-node-self-hashes',n_expected>0 and all(e.get('nodeFingerprint')==vsha(e.get('canonical')) for e in be if isinstance(e,dict)) and len(be)==n_expected)
 ck('builder-adjudication-self-hashes',n_expected>0 and all(e.get('adjudicationFingerprint')==vsha({'schema':'R7_AXE_ADJUDICATION_FINGERPRINT_V1','nodeFingerprint':e.get('nodeFingerprint'),'classification':e.get('classification'),'proofBinding':e.get('proofBinding'),'passed':e.get('passed')}) for e in be if isinstance(e,dict)) and len(be)==n_expected)
 bnodes=[e.get('nodeFingerprint') for e in be if isinstance(e,dict)]; badjs=[e.get('adjudicationFingerprint') for e in be if isinstance(e,dict)]
 proj=[{'nodeFingerprint':e.get('nodeFingerprint'),'adjudicationFingerprint':e.get('adjudicationFingerprint'),'canonical':e.get('canonical'),'classification':e.get('classification'),'proofBinding':e.get('proofBinding'),'passed':e.get('passed')} for e in be if isinstance(e,dict)]
 ck('builder-node-unique',len(set(bnodes))==n_expected); ck('builder-binding-unique',len(set(badjs))==n_expected)
 ck('builder-ordered-node-hash',b.get('orderedNodeFingerprintSha256')==vsha(bnodes)); ck('builder-ordered-adjudication-hash',b.get('orderedAdjudicationFingerprintSha256')==vsha(badjs)); ck('builder-node-set-hash',b.get('nodeFingerprintSetSha256')==vsha(sorted(set(bnodes)))); ck('builder-binding-set-hash',b.get('bindingFingerprintSetSha256')==vsha(sorted(set(badjs)))); ck('builder-inventory-hash',b.get('inventorySha256')==vsha(proj))
 cp=tmp/'contrast-bounds.json'; contrast=load(cp) if cp.is_file() else {}; cvalid=cp.is_file() and valid_contrast(contrast); csha=fsha(cp) if cp.is_file() else None; ck('contrast-proof',cvalid)
 proofs={}; pshas={}
 for width in (1280,390):
  p=tmp/'axe-compensation'/f'home-route-backplates-{width}.json'; data=load(p) if p.is_file() else {}; proofs[width]=data; pshas[width]=fsha(p) if p.is_file() else None; ck(f'backplate-{width}',p.is_file() and valid_backplate(data,width))
 ck('builder-proof-contrast',(b.get('proofDigests') or {}).get('contrast')==csha); ck('builder-proof-1280',(b.get('proofDigests') or {}).get('home1280')==pshas[1280]); ck('builder-proof-390',(b.get('proofDigests') or {}).get('home390')==pshas[390])
 paths=sorted((tmp/'axe').glob('*.json')) if (tmp/'axe').is_dir() else []; ck('exact-report-set',[p.name for p in paths]==EXPECTED_REPORTS)
 entries=[]; summaries=[]; total=Counter(); violations=0
 for p in paths:
  r=load(p); vs=r.get('violations') if isinstance(r.get('violations'),list) else []; inc=r.get('incomplete') if isinstance(r.get('incomplete'),list) else []; violations+=len(vs); fk=Counter()
  if vs: findings.append({'code':'AXE_VIOLATIONS','report':p.name,'count':len(vs)})
  if len(inc)!=1 or not isinstance(inc[0],dict) or inc[0].get('id')!='color-contrast' or not isinstance(inc[0].get('nodes'),list) or not inc[0]['nodes']: findings.append({'code':'INCOMPLETE_RESULT_SET','report':p.name})
  for ri,res in enumerate(inc):
   if not isinstance(res,dict): continue
   for ni,node in enumerate(res.get('nodes') or []):
    if not isinstance(node,dict): continue
    c=canonical_node(p.name,ri,res,ni,node); nf=vsha(c); cl,pb,passed,errs=classify(c,cvalid,csha,proofs,pshas); af=vsha({'schema':'R7_AXE_ADJUDICATION_FINGERPRINT_V1','nodeFingerprint':nf,'classification':cl,'proofBinding':pb,'passed':passed}); e={'report':p.name,'resultIndex':ri,'nodeIndex':ni,'nodeFingerprint':nf,'adjudicationFingerprint':af,'canonical':c,'classification':cl,'proofBinding':pb,'passed':passed,'errors':errs}; entries.append(e); key=str(c.get('messageKey')); fk[key]+=1; total[key]+=1
    if not passed: findings.append({'code':'INDEPENDENT_NODE_ADJUDICATION','report':p.name,'nodeIndex':ni,'errors':errs})
  unsupported=sorted(set(fk)-ALLOWED_KEYS)
  if unsupported: findings.append({'code':'UNSUPPORTED_MESSAGE_KEYS','report':p.name,'keys':unsupported})
  summaries.append({'report':p.name,'rawSha256':fsha(p),'violations':len(vs),'incompleteResults':len(inc),'incompleteNodes':sum(len(x.get('nodes') or []) for x in inc if isinstance(x,dict)),'messageKeys':dict(fk)})
 comparisons=[]
 if ref:
  refs={p.name:p for p in (ref/'axe').glob('*.json')}; ck('reference-report-set',sorted(refs)==EXPECTED_REPORTS)
  for p in paths:
   rp=refs.get(p.name); cr=load(p); rr=load(rp) if rp else None; eq=rr is not None and normalized(cr)==normalized(rr); comparisons.append({'report':p.name,'normalizedEqual':eq,'currentRawSha256':fsha(p),'referenceRawSha256':fsha(rp) if rp else None});
   if not eq: findings.append({'code':'REFERENCE_NORMALIZED_MISMATCH','report':p.name})
  ck('reference-normalized-exact',len(comparisons)==10 and all(x['normalizedEqual'] for x in comparisons))
 nodes=[e['nodeFingerprint'] for e in entries]; adjs=[e['adjudicationFingerprint'] for e in entries]; ns=sorted(set(nodes)); bs=sorted(set(adjs)); projection=[{'nodeFingerprint':e['nodeFingerprint'],'adjudicationFingerprint':e['adjudicationFingerprint'],'canonical':e['canonical'],'classification':e['classification'],'proofBinding':e['proofBinding'],'passed':e['passed']} for e in entries]
 computed={'orderedNodeFingerprintSha256':vsha(nodes),'orderedAdjudicationFingerprintSha256':vsha(adjs),'nodeFingerprintSetSha256':vsha(ns),'bindingFingerprintSetSha256':vsha(bs),'inventorySha256':vsha(projection)}
 ck('zero-violations',violations==0); ck('dynamic-exact-node-count',len(entries)==n_expected and n_expected>0); ck('unique-nodes',len(ns)==n_expected); ck('unique-bindings',len(bs)==n_expected); ck('allowed-message-keys',set(total).issubset(ALLOWED_KEYS)); ck('all-adjudicated',all(e['passed'] and e['errors']==[] for e in entries)); ck('builder-metrics-dynamic',(b.get('metrics') or {}).get('rawFileCount')==10 and (b.get('metrics') or {}).get('totalViolations')==0 and (b.get('metrics') or {}).get('totalIncompleteNodes')==n_expected and (b.get('metrics') or {}).get('uniqueNodeFingerprintCount')==n_expected and (b.get('metrics') or {}).get('uniqueBindingFingerprintCount')==n_expected and (b.get('metrics') or {}).get('messageKeys')==dict(total)); ck('builder-report-semantics',semantic_summaries(b.get('reportSummaries'))==semantic_summaries(summaries)); ck('builder-entries-exact',be==entries)
 if a.label=='authoritative-builder': ck('builder-report-raw-digests',b.get('reportSummaries')==summaries)
 for k,v in computed.items(): ck(f'builder-{k}',b.get(k)==v)
 if be!=entries:
  idx=next((i for i,(x,y) in enumerate(zip(be,entries)) if x!=y),None); findings.append({'code':'BUILDER_ENTRY_MISMATCH','builderCount':len(be),'computedCount':len(entries),'firstMismatchIndex':idx})
 result={'audit':'R7F_INDEPENDENT_AXE_DYNAMIC_FINGERPRINT_V1','label':a.label,'passed':all(checks.values()),'checks':checks,'failedChecks':[k for k,v in checks.items() if not v],'metrics':{'reportCount':len(paths),'violationCount':violations,'nodeCount':len(entries),'messageKeys':dict(total),'minimumStaticContrastRatio':contrast.get('minimumObservedRatio'),**computed},'referenceRawReports':{'tmpRoot':str(ref) if ref else None,'comparisons':comparisons},'builderInventory':{'path':str(bp),'fileSha256':fsha(bp),'schema':b.get('schema'),'inventorySha256':b.get('inventorySha256'),'nodeFingerprintSetSha256':b.get('nodeFingerprintSetSha256'),'bindingFingerprintSetSha256':b.get('bindingFingerprintSetSha256')},'findings':findings}
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n'); print(json.dumps(result,indent=2,ensure_ascii=False)); raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__': main()
