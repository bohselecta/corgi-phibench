"""Append-only fsynced hash chain. Hashes detect alteration, not authorship."""
import fcntl
import json
import os
from pathlib import Path
import time
from .util import canonical, digest

class ReceiptError(ValueError): pass
class ReceiptFull(RuntimeError): pass

class Journal:
    def __init__(self,directory,_lock=None):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=_lock if _lock is not None else (self.directory/'writer.lock').open('a')
        try: fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close(); raise ReceiptError('Run has an active writer')
        self.path=self.directory/'events.jsonl'
        existing=read_events(self.path) if self.path.exists() else []
        if existing and existing[-1]['kind']=='run.finished':
            self.lock.close(); raise ReceiptError('Finalized receipt is immutable')
        self.seq=len(existing)
        self.previous=existing[-1]['hash'] if existing else '0'*64
        self.started=time.monotonic()
        self.base_ms=existing[-1]['elapsed_ms'] if existing else 0
        self.stream=self.path.open('a',encoding='utf8')
    def append(self,kind,payload):
        import signal
        blocked=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:return self._append(kind,payload)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,blocked)

    def _append(self,kind,payload):
        event={'schema':1,'seq':self.seq,'kind':kind,'payload':payload,'previous':self.previous,
               'elapsed_ms':self.base_ms+round((time.monotonic()-self.started)*1000)}
        event['hash']=digest(event)
        line=canonical(event)+'\n'
        terminal=kind in ('run.error','run.finished','workspace.unavailable') or (kind=='workspace.snapshot' and payload.get('label')=='final')
        # Reserve 20 MiB for a complete final snapshot/diff and termination events.
        if not terminal and self.stream.tell()+len(line.encode())>44*1024*1024:raise ReceiptFull('Receipt storage ceiling')
        if self.stream.tell()+len(line.encode())>64*1024*1024:raise ReceiptFull('Final receipt storage ceiling')
        self.stream.write(line); self.stream.flush(); os.fsync(self.stream.fileno())
        self.seq+=1; self.previous=event['hash']
        return event
    def close(self):
        self.stream.close(); self.lock.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

def read_events(path,allow_torn=False):
    path=Path(path)
    if not path.exists(): return []
    if path.stat().st_size>64*1024*1024: raise ReceiptError('Receipt size bound')
    data=path.read_bytes()
    if data and not data.endswith(b'\n'):
        if not allow_torn: raise ReceiptError('Torn receipt tail; use recover')
        data=data[:data.rfind(b'\n')+1]
    events=[]
    previous='0'*64
    elapsed=0
    for seq,line in enumerate(data.splitlines()):
        try:
            event=json.loads(line)
            stored=event['hash']
            unsigned={k:v for k,v in event.items() if k!='hash'}
            if set(unsigned)!={'schema','seq','kind','payload','previous','elapsed_ms'}: raise ValueError()
            if digest(unsigned)!=stored or event['seq']!=seq or event['previous']!=previous or event['schema']!=1: raise ValueError()
            if type(event['elapsed_ms']) is not int or event['elapsed_ms']<elapsed: raise ValueError()
            if seq==0 and event['kind']!='run.started': raise ValueError()
            if events and events[-1]['kind']=='run.finished': raise ValueError()
        except (ValueError,KeyError,TypeError): raise ReceiptError(f'Invalid receipt at event {seq}') from None
        previous=stored; elapsed=event['elapsed_ms']; events.append(event)
    return events

def replay(directory):
    events=read_events(Path(directory)/'events.jsonl')
    if not events: raise ReceiptError('Empty run receipt')
    first=events[0]['payload']
    provider=first.get('provider',{})
    usage={'input_bytes':0,'output_bytes':0,'input_tokens':0,'output_tokens':0,'cost_usd':0}
    token_known=first['mode']=='real-provider'
    cost_known=True
    evaluations=[]; snapshots=[]; contexts=[]
    calls=0; tools=0; inflight=[]; tool_inflight=set()
    status='interrupted'; complete=None; artifact_complete=None; verified=None; total=None
    for e in events:
        p=e['payload']
        if e['kind']=='model.request': calls+=1; inflight.append(p['call']); contexts.append(p)
        if e['kind']=='model.response':
            if p['call'] not in inflight: raise ReceiptError('Unmatched model response')
            inflight.remove(p['call'])
            u=p['usage']
            prices=provider.get('prices_usd_per_million')
            if first['mode']=='real-provider' and prices is not None and u.get('cost_usd') is not None:
                import math
                a,b=u.get('input_tokens'),u.get('output_tokens')
                if type(a) is not int or type(b) is not int or min(a,b)<0:raise ReceiptError('Invalid provider-reported token usage')
                try:estimate=(a*prices['input']+b*prices['output'])/1000000
                except (KeyError,TypeError):raise ReceiptError('Invalid recorded prices') from None
                if not math.isclose(u['cost_usd'],estimate,rel_tol=1e-12,abs_tol=1e-15):raise ReceiptError('Cost estimate differs from recorded prices/tokens')
            for k in usage:
                value=u.get(k)
                if value is None:
                    if k.endswith('tokens'): token_known=False
                    if k=='cost_usd': cost_known=False
                else: usage[k]+=value
        if e['kind']=='run.error' and inflight:
            token_known=False
            if first['mode']=='real-provider': cost_known=False
        if e['kind']=='tool.request':
            if p['call']!=tools+1:raise ReceiptError('Invalid tool attempt sequence')
            tools+=1; tool_inflight.add(p['call'])
        if e['kind']=='tool.result':
            if p['call'] not in tool_inflight:raise ReceiptError('Unmatched tool result')
            tool_inflight.remove(p['call'])
        if e['kind']=='evaluation': evaluations.append(p)
        if e['kind']=='workspace.snapshot':
            if digest(p['files'])!=p['root']: raise ReceiptError('Snapshot hash mismatch')
            snapshots.append({'seq':e['seq'],**p})
        if e['kind']=='run.finished': status=p['status']
    final=[x for x in evaluations if x['stage']=='final']
    if final:
        r=final[-1]['report']['results']
        verified=sum(x['passed'] for x in r); total=len(r); artifact_complete=verified==total and total>0
        complete=artifact_complete and status=='completed'
    if inflight:
        token_known=False
        if first['mode']=='real-provider': cost_known=False
    if not token_known: usage['input_tokens']=usage['output_tokens']=None
    if not cost_known: usage['cost_usd']=None
    tokens=(usage['input_tokens']+usage['output_tokens']) if token_known else None
    efficiency=verified*1000000/tokens if verified is not None and tokens else None
    return {'schema':1,'run':first,'status':status,'complete':complete,'artifact_complete':artifact_complete,'verified':verified,'total':total,
            'model_calls':calls,'tool_calls':tools,'completed_tool_calls':tools-len(tool_inflight),'pending_tool_calls':sorted(tool_inflight),'usage':usage,'efficiency_per_million_tokens':efficiency,
            'events':events,'contexts':contexts,'snapshots':snapshots,'root':events[-1]['hash']}

def recover(directory):
    directory=Path(directory)
    # Acquire lock before changing a torn tail. Retain original bytes for inspection.
    lock=(directory/'writer.lock').open('a')
    try:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ReceiptError('Run has an active writer') from None
        path=directory/'events.jsonl'
        data=path.read_bytes()
        events=read_events(path,allow_torn=True)
        if not events: raise ReceiptError('Cannot recover a receipt without run.started')
        if events[-1]['kind']=='run.finished': return replay(directory)
        if data and not data.endswith(b'\n'):
            torn=directory/'torn-tail.bin'
            if torn.exists(): raise ReceiptError('Existing torn-tail archive; inspect manually')
            with torn.open('xb') as f: f.write(data[data.rfind(b'\n')+1:]); f.flush(); os.fsync(f.fileno())
            with path.open('wb') as f: f.write(data[:data.rfind(b'\n')+1]); f.flush(); os.fsync(f.fileno())
        # Keep the same lock through finalization: no writer can enter a gap
        # between truncation and opening the recovered journal.
        with Journal(directory,_lock=lock) as j:
            j.append('run.error',{'reason':'recovered_after_interruption','usage':'unknown if request was in flight'})
            j.append('run.finished',{'status':'interrupted'})
    finally: lock.close()
    return replay(directory)
