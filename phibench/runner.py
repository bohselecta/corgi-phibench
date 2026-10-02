import dataclasses
from contextlib import ExitStack
from pathlib import Path
import signal
import tempfile
import time
from .policies import Policy
from .providers import FixtureProvider, ProviderFailure, ProviderUnavailable
from .receipts import Journal, replay, ReceiptFull
from .sandbox import Sandbox, SandboxUnavailable
from .util import canonical, digest, restore, snapshot, read_file, write_file
from .evaluator import evaluate

@dataclasses.dataclass(frozen=True)
class Budget:
    calls: int = 16
    tools: int = 64
    wall_seconds: int = 60
    input_bytes: int = 262144
    output_bytes: int = 65536
    context_bytes: int = 32768
    tokens: int = 0
    cost_usd: float = 0
    def validate(self):
        bounds={'calls':(1,128),'tools':(1,512),'wall_seconds':(1,3600),'input_bytes':(1,4194304),
                'output_bytes':(1,1048576),'context_bytes':(128,262144),'tokens':(0,10000000)}
        for k,(lo,hi) in bounds.items():
            v=getattr(self,k)
            if type(v) is not int or not lo<=v<=hi: raise ValueError('Budget bound: '+k)
        import math
        if type(self.cost_usd) not in (int,float) or not math.isfinite(self.cost_usd) or not 0<=self.cost_usd<=1000: raise ValueError('Cost bound')
        return self

class Interrupted(InterruptedError): pass
class BudgetExhausted(RuntimeError): pass

def run(task,method,provider,directory,budget=Budget(),seed=42,protocol=None):
    budget.validate(); method.validate(); task.validate()
    if type(seed) is not int or not 0<=seed<2**32: raise ValueError('Seed bound')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    state=Policy(method,[x['id'] for x in task.public])
    used={'calls':0,'tools':0,'input_bytes':0,'output_bytes':0,'tokens':0,'cost_usd':0}
    finished='failed'
    def remaining():
        left=budget.wall_seconds-(time.monotonic()-start)
        if left<=0: raise TimeoutError('Run wall deadline')
        return left
    def interrupted(sig,frame): raise Interrupted('Signal interruption')
    old={}
    import threading
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT,signal.SIGTERM): old[sig]=signal.signal(sig,interrupted)
    try:
        with Journal(directory) as j, ExitStack() as stack:
            work=None
            first={'version':1,'task':task.view(),'task_hash':task.fingerprint(),'method':dataclasses.asdict(method),
                   'provider':provider.identity,'mode':provider.mode,'budget':dataclasses.asdict(budget),'seed':seed,
                   'toolset':'files-and-isolated-python-v1','evaluator':'oracle-v4','sandbox':Sandbox.version,'protocol':protocol}
            j.append('run.started',first)
            previous_snapshot={}
            def save(label):
                nonlocal previous_snapshot
                import difflib
                files=snapshot(work)
                patches=[]
                for name in sorted(set(previous_snapshot)|set(files)):
                    if previous_snapshot.get(name)!=files.get(name):
                        patches.extend(difflib.unified_diff(previous_snapshot.get(name,'').splitlines(True),files.get(name,'').splitlines(True),fromfile='a/'+name,tofile='b/'+name))
                patch=''.join(patches)
                previous_snapshot=files
                j.append('workspace.snapshot',{'label':label,'root':digest(files),'files':files,'patch':patch})
                return files
            try:
                temp=stack.enter_context(tempfile.TemporaryDirectory(prefix='phibench-'))
                work=Path(temp)/'work'; work.mkdir()
                restore(work,task.initial)
                green=snapshot(work)
                save('initial')
                sandbox=Sandbox()
                j.append('sandbox.ready',sandbox.doctor(work))
                step=0
                tool_observations=[]
                last_critique=''
                def call(phase,targets,feedback=None):
                    if used['calls']>=budget.calls: raise BudgetExhausted('Model call ceiling')
                    request={'contract':'agent-v2','task':task.view(),'targets':targets,'step':step,'phase':phase,
                             'seed':seed,'workspace':snapshot(work),'memory':state.memory(),'feedback':feedback,
                             'tool_observations':tool_observations,'critique':last_critique,
                             'tools':{'read':'relative path','write':'relative UTF-8 file','python':'bounded code in read-only workspace'}}
                    size=len(canonical(request).encode())
                    output=min(8192,budget.output_bytes-used['output_bytes'])
                    if size>budget.context_bytes or size>budget.input_bytes-used['input_bytes'] or output<=0:
                        raise BudgetExhausted('Context/input/output ceiling')
                    if provider.mode=='real-provider':
                        if not provider.authorized or provider.token_ceiling<=0 or provider.cost_ceiling<=0: raise ProviderUnavailable('Runtime NOT RUN')
                        # Conservative bytes upper bound + framing reserve. Reject before spending.
                        reserve=size+8192+output
                        cost=(size+8192)*provider.input_rate/1000000+output*provider.output_rate/1000000
                        if reserve>min(budget.tokens,provider.token_ceiling)-used['tokens'] or cost>min(budget.cost_usd,provider.cost_ceiling)-used['cost_usd']:
                            raise BudgetExhausted('Provider reservation ceiling')
                    call_id=used['calls']+1
                    j.append('model.request',{'call':call_id,'request':request,'input_bytes':size,
                        'components':{k:len(canonical(v).encode()) for k,v in request.items()},'phase':phase})
                    used['calls']+=1
                    result=provider.respond(request,output,min(remaining(),30))
                    response=result['response']; u=result['usage']
                    j.append('model.response',{'call':call_id,'response':response,'usage':u})
                    used['input_bytes']+=u['input_bytes']; used['output_bytes']+=u['output_bytes']
                    used['tokens']+=(u['input_tokens'] or 0)+(u['output_tokens'] or 0)
                    used['cost_usd']+=u['cost_usd'] or 0
                    if provider.mode=='real-provider' and (used['tokens']>provider.token_ceiling or used['cost_usd']>provider.cost_ceiling):
                        raise BudgetExhausted('Provider authorization ceiling exceeded')
                    if used['tokens']>budget.tokens or used['cost_usd']>budget.cost_usd or used['output_bytes']>budget.output_bytes:
                        raise BudgetExhausted('Provider exceeded declared accounting bounds')
                    if not isinstance(response,dict) or len(canonical(response).encode())>output or set(response)-{'calls','critique'}: raise ProviderFailure('Agent response schema')
                    if 'critique' in response and (not isinstance(response['critique'],str) or len(response['critique'])>8192): raise ProviderFailure('Critique bound')
                    calls=response.get('calls',[])
                    if not isinstance(calls,list) or len(calls)>16: raise ProviderFailure('Tool batch bound')
                    if phase=='critique' and calls: raise ProviderFailure('Critic cannot edit or execute')
                    return response
                def tools(response):
                    tool_observations.clear()
                    for c in response.get('calls',[]):
                        if used['tools']>=budget.tools: raise BudgetExhausted('Tool ceiling')
                        remaining()
                        used['tools']+=1
                        j.append('tool.request',{'call':used['tools'],'request':c})
                        try:
                            if not isinstance(c,dict): raise ValueError('Tool mapping')
                            tool=c.get('tool')
                            if tool=='write' and set(c)=={'tool','path','content'}:
                                # Reserve total size before creating the file.
                                if not isinstance(c['path'],str) or not isinstance(c['content'],str):raise ValueError('Path/content strings required')
                                before=snapshot(work); candidate=dict(before); candidate[c['path']]=c['content']
                                if len(candidate)>128 or sum(len(x.encode()) for x in candidate.values())>4194304: raise ValueError('Workspace quota')
                                write_file(work,c['path'],c['content']); snapshot(work)
                                result={'success':True,'path':c['path']}
                            elif tool=='read' and set(c)=={'tool','path'}: result={'success':True,'content':read_file(work,c['path'])}
                            elif tool=='python' and set(c)=={'tool','code'}:
                                p=sandbox.execute(work,c['code'],timeout=remaining())
                                result={'success':p['exit_code']==0,**p}
                            else: raise ValueError('Unsupported tool/schema; shell/git unavailable')
                        except (ValueError,OSError,TypeError,KeyError) as e: result={'success':False,'error':str(e)}
                        j.append('tool.result',{'call':used['tools'],'result':result})
                        tool_observations.append(result)
                while not state.stop():
                    step+=1; targets=state.next()
                    j.append('policy.instruction',{'step':step,'targets':targets,'state':state.state()})
                    response=call('optimize' if method.critique and state.failures else 'implement',targets)
                    tools(response)
                    save('candidate')
                    report=evaluate(task,work,sandbox,timeout=remaining())
                    j.append('evaluation',{'stage':'public','step':step,'report':report})
                    if method.critique:
                        # Only public summaries enter the critic's context; no hidden oracle values.
                        critique=call('critique',targets,{'passed':report['passed'],'failed':[x['id'] for x in report['results'] if not x['passed']]})
                        last_critique=critique.get('critique','')
                        j.append('policy.critique',{'step':step,'critique':last_critique})
                    success=state.observe(report['passed'])
                    if success: green=snapshot(work)
                    elif method.rollback:
                        restore(work,green)
                        save('rollback')
                    j.append('policy.observation',{'step':step,'success':success,'state':state.state()})
                # One final hidden evaluation, no subsequent model call or feedback.
                final=evaluate(task,work,sandbox,hidden=True,timeout=remaining())
                j.append('evaluation',{'stage':'final','report':final})
                finished='completed' if state.stop()=='goal_covered' and final['complete'] else 'failed'
            except ProviderUnavailable:
                finished='unavailable'; j.append('run.error',{'reason':'provider_unavailable','message':'Provider unavailable; execution NOT RUN','mode':provider.mode})
            except SandboxUnavailable:
                finished='unavailable'; j.append('run.error',{'reason':'sandbox_unavailable','message':'Execution unavailable; no host fallback'})
            except (BudgetExhausted,ReceiptFull) as e:
                finished='budget_exhausted'; j.append('run.error',{'reason':str(e)})
            except TimeoutError:
                finished='timeout'; j.append('run.error',{'reason':'timeout','usage':'unknown if provider request in flight'})
            except (Interrupted,KeyboardInterrupt):
                finished='interrupted'; j.append('run.error',{'reason':'interrupted'})
            except Exception as e:
                finished='crashed'; j.append('run.error',{'reason':'execution_error','class':type(e).__name__})
            finally:
                try: save('final')
                except Exception: j.append('workspace.unavailable',{'reason':'Workspace snapshot failed'})
                j.append('run.finished',{'status':finished})
    finally:
        for sig,handler in old.items(): signal.signal(sig,handler)
    return replay(directory)
