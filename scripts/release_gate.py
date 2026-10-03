#!/usr/bin/env python3
"""Independent archive/retained-evidence checks. No provider or publication calls."""
import argparse
import hashlib
from email.parser import BytesParser
import json
from pathlib import Path,PurePosixPath
import re
import sys
import tarfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phibench.experiment import report
from phibench.laboratory import prepare_report
root=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    outcomes={}
    for name,expected in [('success',{'completed':18}),('null',{'failed':18}),('regression',{'completed':6,'failed':12}),('mechanism',{'completed':1}),('crash',{'crashed':18}),('timeout',{'timeout':18})]:
        value=prepare_report(report(root/'examples'/f'{name}-experiment'))
        counts={s:sum(r['status']==s for r in value['rows']) for s in {r['status'] for r in value['rows']}}
        assert counts==expected,(name,counts)
        assert all(r['usage']['input_tokens'] is None and r['usage']['cost_usd']==0 for r in value['rows'])
        outcomes[name]={'protocol':value['protocol'],'scheduled':len(value['rows']),'outcomes':counts}
    dist=root/'dist';wheel=dist/'phibench-0.1.0-py3-none-any.whl';sdist=dist/'phibench-0.1.0.tar.gz'
    blocked={'.private','.work','.verification','.git','.venv','node_modules','.env','.ci-bin','.ci-build','writer.lock','torn-tail.bin'}
    with zipfile.ZipFile(wheel) as archive:
        names=set(archive.namelist());assert {'phibench/laboratory/app.js','phibench/laboratory/style.css','phibench/observatory.html'}<=names
        assert all(n.startswith(('phibench/','phibench-0.1.0.dist-info/')) for n in names)
        metadata=BytesParser().parsebytes(archive.read('phibench-0.1.0.dist-info/METADATA'))
        assert metadata['Name']=='phibench' and metadata['Version']=='0.1.0'
        assert metadata['Requires-Python']=='>=3.11' and metadata['License-Expression']=='Apache-2.0'
        assert metadata.get_all('Requires-Dist') is None
        for name in names:
            p=PurePosixPath(name);assert not p.is_absolute() and '..' not in p.parts and not blocked.intersection(p.parts)
            if name.startswith('phibench/'):assert archive.read(name)==(root/name).read_bytes(),name
    members={}
    with tarfile.open(sdist) as archive:
        for item in archive.getmembers():
            p=PurePosixPath(item.name);assert not p.is_absolute() and '..' not in p.parts and not blocked.intersection(p.parts)
            assert p.parts[0]=='phibench-0.1.0' and not item.issym() and not item.islnk()
            if not item.isfile():continue
            name='/'.join(p.parts[1:]);members[name]=archive.extractfile(item).read()
            if (root/name).is_file():assert members[name]==(root/name).read_bytes(),name
    required=['LICENSE','NOTICE','README.md','RELEASE-CONTRACT.md','docs/PRODUCT-PRESERVATION.md','docs/LABORATORY.md','docs/HISTORY.md','docs/laboratory-desktop.png','docs/laboratory.html','scripts/release_gate.py','tests/browser-laboratory.cjs']
    for name in required:assert name in members,name
    for name in ['success','null','regression','mechanism','crash','timeout']:
        assert f'examples/{name}-experiment/experiment.json' in members
    sums={}
    for line in (dist/'SHA256SUMS').read_text().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  ([^/]+)',line);assert match; sums[match[2]]=match[1]
    for p in [wheel,sdist]:assert sums[p.name]==hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(sums)==2
    # Every relative Markdown link/image resolves in the source archive.
    for path in [root/'README.md',*root.glob('docs/*.md')]:
        for target in re.findall(r'!?\[[^\]]*\]\(([^ )]+)',path.read_text()):
            if '://' in target or target.startswith('#') or target.startswith('mailto:'):continue
            target=target.split('#')[0]
            if target:assert (path.parent/target).exists(),(path,target)
    result={'schema':1,'checks':'PASS','retained_experiments':outcomes,'wheel_members':len(names),'sdist_files':len(members),'artifacts':sums,
            'scope':'Local archive integrity, exact runtime bytes, retained receipt/frozen protocol accounting and links. Hosted release, scientific results and paid runs NOT CHECKED.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
