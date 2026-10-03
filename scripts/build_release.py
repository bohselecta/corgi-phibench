"""Reproducible local artifacts. No upload, provider run, or publication."""
import gzip
import hashlib
import io
import os
from pathlib import Path
import tarfile
import setuptools.build_meta as backend
root=Path(__file__).resolve().parents[1]
os.chdir(root)
# Fixed packaging epoch, not a timestamp claimed for research events.
os.environ.setdefault('SOURCE_DATE_EPOCH','1790985600')
epoch=int(os.environ['SOURCE_DATE_EPOCH'])
dist=root/'dist';dist.mkdir(exist_ok=True)
wheel=dist/backend.build_wheel('dist')
sdist=dist/backend.build_sdist('dist')
buffer=io.BytesIO()
with tarfile.open(sdist,'r:gz') as source,tarfile.open(fileobj=buffer,mode='w',format=tarfile.PAX_FORMAT) as target:
    for item in sorted(source.getmembers(),key=lambda m:m.name):
        item.uid=item.gid=0;item.uname=item.gname='';item.mtime=epoch;item.pax_headers={}
        target.addfile(item,source.extractfile(item) if item.isfile() else None)
with sdist.open('wb') as handle,gzip.GzipFile(fileobj=handle,mode='wb',filename='',mtime=epoch) as compressed:
    compressed.write(buffer.getvalue())
(dist/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted([wheel,sdist])))
print('Local artifacts and checksums built; no publication performed.')
