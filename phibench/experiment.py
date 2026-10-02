import dataclasses
from pathlib import Path
import platform
import sys
from .policies import BUILTINS
from .providers import FixtureProvider
from .runner import Budget, run
from .tasks import TASKS
from .receipts import replay
from .util import atomic_json, digest


def experiment(directory,scenario='success',methods=None,tasks=None,seeds=(42,),budget=Budget(),provider=None):
    directory=Path(directory)
    methods=list(methods or BUILTINS.values())
    tasks=list(tasks or TASKS.values())
    provider=provider or FixtureProvider(scenario)
    if not 1<=len(methods)<=32 or not 1<=len(tasks)<=128 or not 1<=len(seeds)<=32: raise ValueError('Experiment bound')
    if len({x.name for x in methods})!=len(methods) or len({x.id for x in tasks})!=len(tasks): raise ValueError('Duplicate arms/tasks')
    budget.validate()
    for m in methods: m.validate()
    for t in tasks: t.validate()
    if any(type(s) is not int or not 0<=s<2**32 for s in seeds) or len(set(seeds))!=len(seeds): raise ValueError('Seeds')
    directory.mkdir(parents=True,exist_ok=False)
    runs=[{'id':f'run-{ti:03d}-{mi:02d}-{si:02d}','task':t.id,'method':m.name,'seed':s}
          for ti,t in enumerate(tasks) for mi,m in enumerate(methods) for si,s in enumerate(seeds)]
    manifest={'schema':1,'experiment_version':1,'suite':'apparatus-fixtures-v1' if all(t.partition=='demonstration' for t in tasks) else 'operator-supplied-v1',
              'tasks':[{'id':t.id,'hash':t.fingerprint(),'partition':t.partition,'version':t.version} for t in tasks],
              'methods':[dataclasses.asdict(m) for m in methods],'provider':provider.identity,'mode':provider.mode,
              'budget':dataclasses.asdict(budget),'seeds':list(seeds),'runs':runs,
              'tools':'files-and-isolated-python-v1','evaluator':'oracle-v4',
              'environment':{'system':platform.system(),'machine':platform.machine(),'harness_python':sys.version.split()[0]}}
    protocol=digest(manifest)
    atomic_json(directory/'experiment.json',{'protocol':protocol,'manifest':manifest})
    task_map={t.id:t for t in tasks}; method_map={m.name:m for m in methods}
    for spec in runs:
        result=run(task_map[spec['task']],method_map[spec['method']],provider,directory/spec['id'],budget,spec['seed'],protocol)
        if result['status']=='interrupted': break
    return report(directory)


def report(directory):
    import json
    directory=Path(directory)
    frozen=json.loads((directory/'experiment.json').read_text())
    m=frozen['manifest']; protocol=frozen['protocol']
    if digest(m)!=protocol: raise ValueError('Frozen experiment manifest altered')
    rows=[]
    expected_tasks={t['id']:t for t in m['tasks']}
    expected_methods={x['name']:x for x in m['methods']}
    for spec in m['runs']:
        # Run IDs come from untrusted persisted data: never accept path syntax.
        import re
        if not re.fullmatch(r'run-[0-9]{3}-[0-9]{2}-[0-9]{2}',spec['id']): raise ValueError('Run id format')
        path=directory/spec['id']
        if path.is_symlink(): raise ValueError('Symlinked run')
        if not (path/'events.jsonl').exists():
            rows.append({**spec,'status':'not_run','complete':None,'verified':None,'total':None,'usage':None,'receipt':None});continue
        r=replay(path); f=r['run']
        if f['protocol']!=protocol or f['task_hash']!=expected_tasks[spec['task']]['hash'] or f['method']!=expected_methods[spec['method']] or f['seed']!=spec['seed'] or f['provider']!=m['provider'] or f['budget']!=m['budget'] or f['mode']!=m['mode'] or f['toolset']!=m['tools'] or f['evaluator']!=m['evaluator']:
            raise ValueError('Unmatched run fingerprint')
        rows.append({**spec,**{k:r[k] for k in ['status','complete','verified','total','usage','model_calls','tool_calls','efficiency_per_million_tokens']},'receipt':r})
    return {'schema':1,'protocol':protocol,'manifest':m,'rows':rows,
            'interpretation':'Deterministic fixture apparatus checks; no evidence of model ability or policy superiority.' if m['mode']=='fixture' else 'Real-provider run records; review protocol and every failure before inference.'}
