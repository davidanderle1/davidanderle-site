#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, stat
from pathlib import Path

SOURCE_EXCLUDED_TOP={'.git','node_modules','dist','.astro','.r7e-tmp'}
SOURCE_EXCLUDED_PREFIXES=('public/assets/portrait/','public/assets/js/','public/artifacts/','src/data/generated/')

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def skip_source(rel: str) -> bool:
    parts=rel.split('/')
    return bool(parts and parts[0] in SOURCE_EXCLUDED_TOP) or rel.startswith(SOURCE_EXCLUDED_PREFIXES)

def scan(root: Path, source_mode: bool=False):
    root=root.resolve()
    rows=[]
    for p in sorted(root.rglob('*'), key=lambda p:p.relative_to(root).as_posix()):
        rel=p.relative_to(root).as_posix()
        if source_mode and skip_source(rel):
            continue
        st=p.lstat()
        mode=stat.S_IMODE(st.st_mode)
        if p.is_symlink():
            rows.append({'path':rel,'type':'symlink','mode':oct(mode),'target':os.readlink(p)})
        elif p.is_file():
            rows.append({'path':rel,'type':'file','mode':oct(mode),'size':st.st_size,'sha256':sha256_file(p)})
    return rows

def digest(rows):
    blob=(json.dumps(rows, sort_keys=True, separators=(',',':'))+'\n').encode()
    return hashlib.sha256(blob).hexdigest()

def write_manifest(root: Path, out: Path, source_mode: bool):
    rows=scan(root,source_mode)
    result={'root':str(root),'sourceMode':source_mode,'entryCount':len(rows),'treeSha256':digest(rows),'entries':rows}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'entryCount':len(rows),'treeSha256':result['treeSha256'],'output':str(out)},indent=2))

def compare(a: Path,b: Path,out: Path,source_mode: bool):
    ma=scan(a,source_mode); mb=scan(b,source_mode)
    da={x['path']:x for x in ma}; db={x['path']:x for x in mb}
    only_a=sorted(set(da)-set(db)); only_b=sorted(set(db)-set(da))
    changed=sorted(p for p in set(da)&set(db) if da[p]!=db[p])
    result={
      'passed':not only_a and not only_b and not changed,
      'sourceMode':source_mode,
      'a':{'root':str(a),'entryCount':len(ma),'treeSha256':digest(ma)},
      'b':{'root':str(b),'entryCount':len(mb),'treeSha256':digest(mb)},
      'onlyA':only_a,'onlyB':only_b,'changed':changed
    }
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(1)

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest='cmd',required=True)
    m=sub.add_parser('manifest'); m.add_argument('root',type=Path); m.add_argument('output',type=Path); m.add_argument('--source',action='store_true')
    c=sub.add_parser('compare'); c.add_argument('a',type=Path); c.add_argument('b',type=Path); c.add_argument('output',type=Path); c.add_argument('--source',action='store_true')
    args=ap.parse_args()
    if args.cmd=='manifest': write_manifest(args.root,args.output,args.source)
    else: compare(args.a,args.b,args.output,args.source)
if __name__=='__main__': main()
