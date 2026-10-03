"""Receipt-backed laboratory projections. No evaluator or provider is executed."""
from copy import deepcopy
import dataclasses
import re
from .policies import BUILTINS, Method
from .receipts import replay_events
from .util import digest, canonical
from .runner import Budget


def file_versions(events):
    """Link saved full-file versions to recorded writes; preserve rollback lineage.

    This does not infer token authorship, surviving generated lines or test relevance.
    """
    versions = []
    roots = {}
    previous = {}
    origins = {}
    attempts = {}
    writes = {}
    model_call = None
    step = None
    for event in events:
        seq, kind, p = event['seq'], event['kind'], event['payload']
        if kind == 'policy.instruction': step = p['step']
        if kind == 'model.response': model_call = p['call']
        if kind == 'tool.request':
            attempts[p['call']] = (seq, p['request'], model_call, step)
        if kind == 'tool.result' and p['result'].get('success'):
            attempt = attempts.get(p['call'])
            if attempt and attempt[1].get('tool') == 'write':
                req_seq, req, call, shell = attempt
                writes[req['path']] = {'event':req_seq, 'model_call':call,
                    'step':shell, 'content':req['content']}
        if kind != 'workspace.snapshot': continue
        files = p['files']
        if p['label'] == 'rollback' and p['root'] in roots:
            origins = deepcopy(roots[p['root']])
        else:
            current = {}
            for name, content in files.items():
                if name in previous and previous[name] == content:
                    current[name] = origins[name]
                elif name in writes and writes[name]['content'] == content:
                    current[name] = {'kind':'recorded full-file write',
                        **{k:v for k,v in writes[name].items() if k != 'content'},
                        'observed_snapshot':seq}
                else:
                    current[name] = {'kind':'initial task' if p['label']=='initial'
                        else 'snapshot; write origin unknown', 'observed_snapshot':seq,
                        'event':seq,'model_call':None,'step':None}
            origins = current
        roots[p['root']] = deepcopy(origins)
        versions.append({'seq':seq,'files':deepcopy(origins)})
        previous = files
    return versions


def prepare_report(value):
    """Reconstruct summaries and validate protocol/journals before claiming integrity."""
    manifest, protocol = value['manifest'], value['protocol']
    if value.get('schema') != 1 or digest(manifest) != protocol:
        raise ValueError('Frozen experiment manifest altered')
    if manifest.get('schema') != 1 or manifest.get('experiment_version') != 1:
        raise ValueError('Manifest version')
    Budget(**manifest['budget']).validate()
    if manifest['mode'] not in ('fixture','real-provider'):
        raise ValueError('Unknown experiment evidence mode')
    specs = manifest['runs']
    if not 1 <= len(specs) <= 4096: raise ValueError('Laboratory supports 1–4096 scheduled runs')
    if len({s['id'] for s in specs}) != len(specs):
        raise ValueError('Duplicate scheduled run')
    rows = {r['id']:r for r in value['rows']}
    if len(rows) != len(value['rows']) or set(rows) != {s['id'] for s in specs}:
        raise ValueError('Laboratory rows differ from scheduled runs')
    tasks = {t['id']:t for t in manifest['tasks']}
    methods = {m['name']:m for m in manifest['methods']}
    if len(tasks) != len(manifest['tasks']) or len(methods) != len(manifest['methods']):
        raise ValueError('Duplicate task or method')
    for m in methods.values(): Method(**m).validate()
    result = []
    for spec in specs:
        if not re.fullmatch(r'run-[0-9]{3}-[0-9]{2}-[0-9]{2}',spec['id']):
            raise ValueError('Run id format')
        row = rows[spec['id']]
        if row.get('receipt') is None:
            result.append({**spec,'status':'not_run','complete':None,'verified':None,
                           'total':None,'usage':None,'receipt':None})
            continue
        events = row['receipt']['events']
        if not isinstance(events,list) or len(events) > 20000:
            raise ValueError('Laboratory supports <=20000 events per run')
        receipt = replay_events(events)
        for event in events:
            if event['kind'] != 'model.request': continue
            p = event['payload']
            components = {k:len(canonical(v).encode()) for k,v in p['request'].items()}
            if p['components'] != components or p['input_bytes'] != len(canonical(p['request']).encode()):
                raise ValueError('Context measurement differs from recorded request')
        if receipt['status'] not in ('completed','failed','interrupted','unavailable'):
            raise ValueError('Unknown run status')
        first = receipt['run']
        expected = {'protocol':protocol,'task_hash':tasks[spec['task']]['hash'],
            'method':methods[spec['method']],'seed':spec['seed'],'provider':manifest['provider'],
            'budget':manifest['budget'],'mode':manifest['mode'],'toolset':manifest['tools'],
            'evaluator':manifest['evaluator']}
        if any(first.get(k) != v for k,v in expected.items()):
            raise ValueError('Unmatched run fingerprint')
        receipt['file_versions'] = file_versions(receipt['events'])
        result.append({**spec,**{k:receipt[k] for k in ('status','complete','verified','total',
            'usage','model_calls','tool_calls','efficiency_per_million_tokens')},'receipt':receipt})
    return {'schema':1,'protocol':protocol,'manifest':manifest,'rows':result,
        'interpretation':('Deterministic fixture apparatus checks; no evidence of model ability '
                         'or policy superiority. Real-model comparative evidence: NOT RUN.'
                         if manifest['mode']=='fixture' else
                         'Retained real-provider evidence. Review the full protocol and every failure; '
                         'receipt integrity does not establish the evaluator or model claims.'),
        'verification':{'state':'PASS','scope':'Frozen protocol, receipt hash chains, snapshots and '
                       'reconstructed accounting checked in Python at export. Code reevaluation '
                       'is a separate phibench verify command. Hashes do not establish authorship.'},
        'method_templates':[dataclasses.asdict(m) for m in BUILTINS.values()]}
