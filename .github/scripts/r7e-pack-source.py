#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, datetime as dt, hashlib, json, os, stat, zipfile
from pathlib import Path

EXCLUDED_TOP_LEVEL_DIRS={'.git','node_modules','dist','.astro','.r7e-tmp'}
EXCLUDED_PREFIXES=('public/assets/portrait/','public/assets/js/','public/artifacts/','src/data/generated/')

def sha256_bytes(b: bytes)->str:
    return hashlib.sha256(b).hexdigest()
def sha256_file(p: Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def included(source: Path):
    out=[]
    for p in source.rglob('*'):
        rel=p.relative_to(source)
        if rel.parts and rel.parts[0] in EXCLUDED_TOP_LEVEL_DIRS: continue
        r=rel.as_posix()
        if r.startswith(EXCLUDED_PREFIXES): continue
        if p.is_symlink():
            raise SystemExit(f'symlink not permitted in canonical source: {r}')
        if p.is_file(): out.append(p)
    return sorted(out,key=lambda p:p.relative_to(source).as_posix())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--chunk-size',type=int,default=60000)
    args=ap.parse_args()
    source=args.source.resolve()
    if not (source/'package.json').is_file() or not (source/'package-lock.json').is_file():
        raise SystemExit('complete canonical source required')
    epoch=int(os.environ.get('SOURCE_DATE_EPOCH','1787961600'))
    stamp=dt.datetime.fromtimestamp(epoch,dt.timezone.utc)
    zip_stamp=(stamp.year,stamp.month,stamp.day,stamp.hour,stamp.minute,stamp.second)
    files=included(source)
    args.archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9,strict_timestamps=True) as z:
        for p in files:
            rel=p.relative_to(source).as_posix()
            info=zipfile.ZipInfo(rel,date_time=zip_stamp)
            info.create_system=3
            mode=0o755 if p.stat().st_mode & stat.S_IXUSR else 0o644
            info.external_attr=((stat.S_IFREG|mode)&0xffff)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(args.archive) as z:
        bad=z.testzip()
        if bad: raise SystemExit(f'zip corrupt at {bad}')
    encoded=base64.b64encode(args.archive.read_bytes()).decode('ascii')
    args.output.mkdir(parents=True,exist_ok=True)
    for p in args.output.glob('part*.b64'): p.unlink()
    for n in ('SHA256SUMS','ARCHIVE_SHA256','SOURCE_TREE.json'):
        p=args.output/n
        if p.exists(): p.unlink()
    parts=[]
    for i,start in enumerate(range(0,len(encoded),args.chunk_size),1):
        p=args.output/f'part{i:04d}.b64'
        p.write_text(encoded[start:start+args.chunk_size]+'\n',encoding='ascii',newline='\n')
        parts.append(p)
    archive_sha=sha256_file(args.archive)
    (args.output/'ARCHIVE_SHA256').write_text(archive_sha+'\n')
    tree=[]
    for p in files:
        rel=p.relative_to(source).as_posix()
        tree.append({'path':rel,'sha256':sha256_file(p),'mode':oct(p.stat().st_mode & 0o777),'size':p.stat().st_size})
    (args.output/'SOURCE_TREE.json').write_text(json.dumps({'fileCount':len(tree),'files':tree},indent=2)+'\n')
    manifest_files=[*parts,args.output/'ARCHIVE_SHA256',args.output/'SOURCE_TREE.json']
    (args.output/'SHA256SUMS').write_text(''.join(f'{sha256_file(p)}  .r7e-source/{p.name}\n' for p in manifest_files))
    print(json.dumps({'sourceFiles':len(files),'archiveSha256':archive_sha,'archiveBytes':args.archive.stat().st_size,'encodedChars':len(encoded),'parts':len(parts)},indent=2))
if __name__=='__main__': main()
