import argparse
import dataclasses
import json
from pathlib import Path
import sys
import tempfile
from . import __version__
from .experiment import experiment, report
from .policies import BUILTINS,load_method
from .providers import FixtureProvider, OpenAICompatible
from .receipts import replay,recover
from .runner import Budget,run
from .sandbox import Sandbox
from .tasks import TASKS
from .util import canonical,atomic_json
from .view import export_html

def load_task(path):
    from .tasks import Task
    if path.stat().st_size>1048576:raise ValueError('Task file <= 1 MiB required')
    data=json.loads(path.read_text())
    data['public']=tuple(data['public']);data['hidden']=tuple(data['hidden'])
    return Task(**data).validate()

def main(argv=None):
    parser=argparse.ArgumentParser(prog='phibench',description='Matched control policies. Fixture runs are apparatus checks, not model evidence.')
    parser.add_argument('--version',action='version',version=__version__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('methods')
    p=sub.add_parser('validate-method');p.add_argument('file')
    for cmd in ('demo','run'):
        p=sub.add_parser(cmd)
        p.add_argument('--out',type=Path,required=True)
        p.add_argument('--scenario',choices=('success','null','regression','crash','timeout'),default='success')
        p.add_argument('--method',choices=list(BUILTINS),default='phishell')
        p.add_argument('--method-file',type=Path)
        p.add_argument('--task',choices=list(TASKS),default='bugfix')
        p.add_argument('--task-file',type=Path)
        p.add_argument('--fixture-script',type=Path)
        p.add_argument('--seed',type=int,default=42)
        p.add_argument('--calls',type=int,default=16);p.add_argument('--wall-seconds',type=int,default=60)
        p.add_argument('--endpoint');p.add_argument('--model',default='unspecified')
        p.add_argument('--authorize-runtime',action='store_true')
        p.add_argument('--tokens',type=int,default=0);p.add_argument('--cost-usd',type=float,default=0)
        p.add_argument('--input-price',type=float,default=0);p.add_argument('--output-price',type=float,default=0)
    for cmd in ('report','replay','recover','observe','verify'):
        p=sub.add_parser(cmd);p.add_argument('path',type=Path)
        if cmd=='verify':p.add_argument('--task-file',type=Path)
        if cmd=='observe':p.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='doctor':
            with tempfile.TemporaryDirectory() as d: print(canonical(Sandbox().doctor(d)))
        elif args.command=='methods':
            for m in BUILTINS.values(): print(f'{m.name:<16} {m.growth:<12} {m.memory:<6} rollback={str(m.rollback).lower()}')
        elif args.command=='validate-method':print(canonical(dataclasses.asdict(load_method(args.file and Path(args.file).read_text()))))
        elif args.command in ('demo','run'):
            budget=Budget(calls=args.calls,wall_seconds=args.wall_seconds,tokens=args.tokens,cost_usd=args.cost_usd)
            if args.fixture_script and args.fixture_script.stat().st_size>1048576:raise ValueError('Fixture script bound')
            provider=FixtureProvider(args.scenario,json.loads(args.fixture_script.read_text()) if args.fixture_script else None)
            if args.endpoint:
                if args.fixture_script:raise ValueError('Fixture scripts cannot be sent to a real provider')
                if args.scenario!='success':raise ValueError('Fixture scenarios cannot label real-provider runs')
                provider=OpenAICompatible(args.endpoint,args.model,args.authorize_runtime,args.tokens,args.cost_usd,args.input_price,args.output_price)
            method=load_method(args.method_file.read_text()) if args.method_file else BUILTINS[args.method]
            task=load_task(args.task_file) if args.task_file else TASKS[args.task]
            if args.command=='demo':
                methods=[method] if args.method_file else None
                result=experiment(args.out,args.scenario,methods=methods,tasks=[task] if args.task_file else None,seeds=(args.seed,),budget=budget,provider=provider)
                export_html(result,args.out/'observatory.html')
                atomic_json(args.out/'report.json',{**result,'rows':[{k:v for k,v in x.items() if k!='receipt'} for x in result['rows']]})
                print('PhiBench · '+provider.mode+' · protocol '+result['protocol'][:16])
                for r in result['rows']:
                    checks='unknown' if r['total'] is None else f"{r['verified']}/{r['total']}"
                    print(f"{r['task']:<10} {r['method']:<16} {r['status']:<18} checks={checks}")
                print('Model evidence: NOT RUN' if provider.mode=='fixture' else 'Review retained real-provider receipts.')
                print('Observatory: '+str((args.out/'observatory.html').resolve()))
            else:
                r=run(task,method,provider,args.out,budget,args.seed)
                print(canonical({k:v for k,v in r.items() if k not in ('events','contexts','snapshots')}))
                return 0 if r['status']=='completed' else 2
        elif args.command=='report':
            r=report(args.path);print(canonical({**r,'rows':[{k:v for k,v in x.items() if k!='receipt'} for x in r['rows']]}))
        elif args.command in ('replay','recover'):
            r=replay(args.path) if args.command=='replay' else recover(args.path)
            print(canonical({k:v for k,v in r.items() if k not in ('events','contexts','snapshots')}))
        elif args.command=='verify':
            from .evaluator import verify_saved
            r=report(args.path)
            task_map=dict(TASKS)
            if args.task_file:
                task=load_task(args.task_file);task_map[task.id]=task
            results=[]
            for row in r['rows']:
                result=verify_saved(args.path/row['id'],task_map[row['task']]) if row['receipt'] else {'status':'NOT_RUN','reason':'No receipt'}
                results.append({'run':row['id'],**result})
            print(canonical(results))
            return 2 if any(x['status']=='FAIL' for x in results) else 0
        elif args.command=='observe':
            export_html(report(args.path),args.out);print(str(args.out.resolve()))
        return 0
    except (ValueError,RuntimeError,OSError,TypeError,KeyError) as e:
        print('phibench: '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
