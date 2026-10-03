#!/usr/bin/env python3
"""Export retained public demo receipts. Never copies a workspace or runs inference."""
from pathlib import Path
import json
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phibench.experiment import report
from phibench.view import export_html

def main():
    source,destination,html=map(Path,sys.argv[1:])
    if destination.exists():raise SystemExit('Destination exists; retained experiments are immutable')
    value=report(source)
    destination.mkdir(parents=True)
    shutil.copyfile(source/'experiment.json',destination/'experiment.json')
    for spec in value['manifest']['runs']:
        journal=source/spec['id']/'events.jsonl'
        if journal.exists():
            (destination/spec['id']).mkdir()
            shutil.copyfile(journal,destination/spec['id']/'events.jsonl')
    export_html(report(destination),html)
    print(json.dumps({'source':str(source),'destination':str(destination),'protocol':value['protocol'],
        'runs':len(value['rows']),'status':{s:sum(r['status']==s for r in value['rows']) for s in sorted({r['status'] for r in value['rows']})}},indent=2))
if __name__=='__main__':main()
