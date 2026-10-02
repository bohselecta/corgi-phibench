"""Black-box acceptance: CLI, real signals, hard crash recovery, installed artifacts.

Runs in a separate process. This is independently framed black-box verification,
not a claim that its author is an independent human reviewer.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]

def cli(*args):
    p=subprocess.run([sys.executable,'-m','phibench',*args],cwd=ROOT,text=True,capture_output=True,timeout=60)
    assert p.returncode==0,(args,p.stderr)
    return p.stdout

with tempfile.TemporaryDirectory(prefix='phi-accept-') as temp:
    root=Path(temp)
    assert json.loads(cli('doctor'))['status']=='PASS'
    exp=root/'experiment'
    output=cli('demo','--out',str(exp))
    assert output.count('completed')==18,output
    rows=json.loads(cli('report',str(exp)))['rows']
    assert len(rows)==18 and all(r['complete'] and r['verified']==r['total']==7 for r in rows)
    assert all(r['usage']['input_tokens'] is None and r['usage']['cost_usd']==0 for r in rows)
    checks=json.loads(cli('verify',str(exp)))
    assert len(checks)==18 and all(c['status']=='PASS' for c in checks)
    html=root/'reopened.html'
    cli('observe',str(exp),'--out',str(html))
    assert 'Deterministic fixture apparatus' in html.read_text()
    first=exp/'run-000-00-00'
    a=json.loads(cli('replay',str(first)));b=json.loads(cli('replay',str(first)))
    assert a==b and a['status']=='completed'
    # Exercise real SIGTERM and SIGKILL while a model request is in flight.
    for sig in (signal.SIGTERM,signal.SIGKILL):
        dest=root/str(sig)
        script='''import time
from phibench.runner import run
from phibench.tasks import TASKS
from phibench.policies import BUILTINS
from phibench.providers import FixtureProvider
class Waiting(FixtureProvider):
    def respond(self,*args):
        time.sleep(30)
run(TASKS['bugfix'],BUILTINS['phishell'],Waiting(),DEST)
'''.replace('DEST',repr(str(dest)))
        p=subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        journal=dest/'events.jsonl'
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if journal.exists() and 'model.request' in journal.read_text():break
            if p.poll() is not None:raise AssertionError(p.communicate())
            time.sleep(.025)
        else:p.kill();raise AssertionError('No durable model.request')
        p.send_signal(sig);p.communicate(timeout=5)
        if sig==signal.SIGKILL:cli('recover',str(dest))
        receipt=json.loads(cli('replay',str(dest)))
        assert receipt['status']=='interrupted' and receipt['model_calls']==1,receipt
        assert receipt['complete'] is None
        assert receipt['usage']['input_tokens'] is None
    # A hard crash in a tool consumes an attempt even without a returned result.
    dest=root/'tool-kill'
    script='''from phibench.runner import run
from phibench.tasks import TASKS
from phibench.policies import BUILTINS
from phibench.providers import FixtureProvider
script={'calls':[{'tool':'python','code':'while True:pass'}]}
run(TASKS['bugfix'],BUILTINS['phishell'],FixtureProvider(script=script),DEST)
'''.replace('DEST',repr(str(dest)))
    p=subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        journal=dest/'events.jsonl'
        if journal.exists() and 'tool.request' in journal.read_text():break
        if p.poll() is not None:raise AssertionError(p.communicate())
        time.sleep(.01)
    else:p.kill();raise AssertionError('No durable tool.request')
    p.kill();p.communicate(timeout=5)
    receipt=json.loads(cli('recover',str(dest)))
    assert receipt['status']=='interrupted' and receipt['tool_calls']==1,receipt
    assert receipt['completed_tool_calls']==0 and receipt['pending_tool_calls']==[1],receipt
    print('PASS: 18 matched executions, 18 independent score reconstructions, offline replay/export, SIGTERM, SIGKILL model/tool recovery; no provider calls.')
