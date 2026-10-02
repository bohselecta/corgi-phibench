"""The host oracle scores outputs; expected answers are never mounted in execution."""
import ast
import json
import time
from collections import Counter
from .util import canonical, snapshot

BRIDGE = '''import sys, json, importlib.util
requests=json.load(sys.stdin)
spec=importlib.util.spec_from_file_location('candidate','/work/solution.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
results=[]
for request in requests:
    original=json.dumps(request['args'],sort_keys=True)
    try:
        value=getattr(module,request['function'])(*request['args'])
        result={'value':value}
        if request.get('unchanged_args'):result['unchanged']=original==json.dumps(request['args'],sort_keys=True)
        results.append(result)
    except BaseException as error:
        results.append({'raises':type(error).__name__})
print(json.dumps(results, allow_nan=False))
'''

def bounded_tree(source):
    if len(source.encode())>65536:return None,None
    tree=ast.parse(source)
    nodes=[]
    for n in ast.walk(tree):
        nodes.append(n)
        if len(nodes)>4096:return None,None
    return tree,nodes

def preservation_proven(source, function):
    """Conservatively prove no JSON argument mutation in a small Python grammar.

    Runtime observations come from untrusted candidate code. Only this host-side
    syntax proof can authorize a preservation check; unsupported code fails it.
    """
    try:
        tree,nodes=bounded_tree(source)
        if tree is None:return False
        body=[n for n in tree.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))]
        if len(body)!=1 or not isinstance(body[0],ast.FunctionDef):return False
        fn=body[0]
        if fn.name!=function or fn.decorator_list or fn.returns or fn.type_comment:return False
        a=fn.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.defaults or a.kw_defaults:return False
        params={x.arg for x in a.posonlyargs+a.args}
        if any(x.annotation for x in a.posonlyargs+a.args):return False
        stores=Counter(n.id for n in nodes if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store))
        if 'len' in params or 'len' in stores or fn.name=='len':return False
        fresh={n.targets[0].id for n in nodes if isinstance(n,ast.Assign)
               and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
               and isinstance(n.value,ast.List) and not n.value.elts
               and stores[n.targets[0].id]==1 and n.targets[0].id not in params}
        names=params|set(stores)|{'len'}
        called_attributes={id(n.func) for n in nodes if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
        allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.Assign,
                 ast.For,ast.If,ast.Expr,ast.Name,ast.Load,ast.Store,ast.List,ast.Tuple,
                 ast.Constant,ast.Compare,ast.BoolOp,ast.UnaryOp,ast.BinOp,ast.Subscript,
                 ast.Slice,ast.IfExp,ast.Call,ast.Attribute,ast.Break,ast.Continue,ast.Pass,
                 ast.cmpop,ast.boolop,ast.unaryop,ast.operator)
        for n in nodes:
            if not isinstance(n,allowed):return False
            if isinstance(n,ast.FunctionDef) and n is not fn:return False
            if isinstance(n,ast.Name) and n.id not in names:return False
            if isinstance(n,ast.Assign) and (len(n.targets)!=1 or not isinstance(n.targets[0],ast.Name)):return False
            if isinstance(n,(ast.Subscript,ast.Attribute)) and not isinstance(n.ctx,ast.Load):return False
            if isinstance(n,ast.Constant) and type(n.value) not in (str,int,float,bool,type(None)):return False
            if isinstance(n,ast.Call):
                if n.keywords:return False
                if isinstance(n.func,ast.Name):
                    if n.func.id!='len' or len(n.args)!=1:return False
                elif isinstance(n.func,ast.Attribute):
                    if not (n.func.attr=='append' and isinstance(n.func.value,ast.Name)
                            and n.func.value.id in fresh and len(n.args)==1):return False
                else:return False
            if isinstance(n,ast.Attribute) and id(n) not in called_attributes:return False
        return True
    except (SyntaxError,ValueError,TypeError,RecursionError):return False

def structural(source):
    try:
        tree,nodes=bounded_tree(source)
        if tree is None:return False
        functions={x.name:x for x in tree.body if isinstance(x,ast.FunctionDef)}
        for name in ('greet','farewell'):
            calls=[x for x in ast.walk(functions[name]) if isinstance(x,ast.Call)]
            if not any(isinstance(x.func,ast.Name) and x.func.id=='normalize_name' for x in calls): return False
            if any(isinstance(x.func,ast.Attribute) and x.func.attr in ('split','strip','title') for x in calls): return False
        return 'normalize_name' in functions
    except (SyntaxError,KeyError,RecursionError): return False

def evaluate(task,workspace,sandbox,hidden=False,timeout=None):
    deadline=time.monotonic()+(sandbox.timeout if timeout is None else timeout)
    def remaining():
        left=deadline-time.monotonic()
        if left<=0:raise TimeoutError('Evaluation total deadline')
        return left
    files=snapshot(workspace)
    criteria=list(task.public) + (list(task.hidden) if hidden else [])
    functional=[x for x in criteria if not x.get('structural')]
    requests=[{'function':x['function'],'args':x['args'],'unchanged_args':x.get('unchanged_args',False)} for x in functional]
    proofs={}
    source=files.get('solution.py','')
    for c in functional:
        if c.get('unchanged_args') and c['function'] not in proofs:
            remaining();proofs[c['function']]=preservation_proven(source,c['function']);remaining()
    process=sandbox.execute(workspace,BRIDGE,canonical(requests).encode(),timeout=remaining())
    remaining()
    outputs=[]
    if process['exit_code']==0:
        try:
            outputs=json.loads(process['stdout'])
            if not isinstance(outputs,list) or len(outputs)!=len(functional): outputs=[]
        except (ValueError,TypeError): pass
    results=[]
    for i,c in enumerate(functional):
        remaining()
        expected = c['expected'] if isinstance(c['expected'],dict) and 'raises' in c['expected'] else {'value':c['expected']}
        if c.get('unchanged_args'):expected={**expected,'unchanged':True}
        proven=not c.get('unchanged_args') or proofs[c['function']]
        passed = proven and i<len(outputs) and canonical(outputs[i])==canonical(expected)
        results.append({'id':c['id'],'hidden':c in task.hidden,'passed':passed})
    for c in criteria:
        remaining()
        if c.get('structural'): results.append({'id':c['id'],'hidden':False,'passed':structural(source)})
    remaining()
    return {'version':'oracle-v4','results':results,'process':process,
            'passed':[x['id'] for x in results if x['passed'] and not x['hidden']],
            'complete':all(x['passed'] for x in results) and bool(results)}

def verify_saved(directory,task):
    """Fresh process verification from retained final artifact, without a provider."""
    import tempfile
    from .receipts import replay
    from .util import restore
    from .sandbox import Sandbox
    r=replay(directory)
    if r['run']['task_hash']!=task.fingerprint(): raise ValueError('Task version/hash differs')
    final=[e['payload']['report'] for e in r['events'] if e['kind']=='evaluation' and e['payload']['stage']=='final']
    if not final: return {'status':'NOT_RUN','reason':'No final evaluation was retained'}
    if not r['snapshots']: raise ValueError('Missing final snapshot')
    with tempfile.TemporaryDirectory(prefix='phibench-verify-') as d:
        restore(d,r['snapshots'][-1]['files'])
        actual=evaluate(task,d,Sandbox(),hidden=True)
    matches=actual['results']==final[-1]['results']
    return {'status':'PASS' if matches else 'FAIL','retained':final[-1]['results'],'recomputed':actual['results']}
