"""Provider contract. Fixture units are bytes; model usage is never estimated."""
import json
import os
import urllib.request
import urllib.parse
import signal
import threading
import math
from contextlib import contextmanager
from .util import canonical

class ProviderUnavailable(RuntimeError): pass
class ProviderFailure(RuntimeError): pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # A redirect changes the authorized/provenanced endpoint and may forward
        # credentials. Reject before constructing or sending another request.
        if fp is not None:fp.close()
        raise ProviderFailure('Provider redirects are not allowed')

def http_open(request,timeout):
    # Per-request policy; never replace the application's global urllib opener.
    return urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout)

@contextmanager
def request_deadline(timeout):
    # Socket timeouts only bound inactivity, so enforce a total monotonic timer.
    # Do not replace another application's active alarm or silently run unbounded.
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal,'setitimer'):
        raise ProviderUnavailable('Bounded provider requests require the POSIX main thread')
    if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK,set()):
        raise ProviderUnavailable('A blocked alarm prevents bounded provider execution')
    if not math.isfinite(timeout) or timeout<=0:raise TimeoutError('Provider total deadline')
    if signal.getitimer(signal.ITIMER_REAL)[0]:raise ProviderUnavailable('An existing alarm prevents bounded provider execution')
    def expired(sig,frame):raise TimeoutError('Provider total deadline')
    previous=signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,timeout)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)

SOLUTIONS = {
    'bugfix':'def clamp(value, low, high):\n    if low > high:\n        raise ValueError("inverted bounds")\n    return max(low, min(value, high))\n',
    'feature':'def stable_unique(items):\n    result = []\n    for item in items:\n        if item not in result:\n            result.append(item)\n    return result\n',
    'refactor':'def normalize_name(value):\n    return " ".join(value.strip().split()).title()\n\ndef greet(value):\n    return "Hello, " + normalize_name(value)\n\ndef farewell(value):\n    return "Bye, " + normalize_name(value)\n',
}
class FixtureProvider:
    mode = 'fixture'
    def __init__(self, scenario='success',script=None):
        if scenario not in ('success','null','crash','timeout','regression'): raise ValueError('Fixture scenario')
        self.scenario=scenario
        self.script=script
        if script is not None:
            if not isinstance(script,dict) or len(canonical(script).encode())>1048576:raise ValueError('Fixture script bound')
        self.identity={'provider':'deterministic-fixture','model':'script-v1','scenario':scenario,'tokenizer':None}
        if script is not None:
            from .util import digest
            self.identity['script_hash']=digest(script)
    def respond(self, request, max_output, timeout):
        if self.scenario=='crash': raise ProviderFailure('Deliberate fixture crash')
        if self.scenario=='timeout': raise TimeoutError('Deliberate fixture timeout')
        if request['phase']=='critique': response={'calls':[],'critique':'Check public feedback and preserve accepted behavior.'}
        elif self.scenario=='null': response={'calls':[]}
        elif self.script is not None:response=self.script
        else:
            if request['task']['id'] not in SOLUTIONS:raise ProviderUnavailable('Fixture has no solution for this task')
            content = SOLUTIONS[request['task']['id']]
            if self.scenario=='regression' and request['step']>1: content='raise RuntimeError("fixture regression")\n'
            response={'calls':[{'tool':'write','path':'solution.py','content':content}]}
        raw=canonical(response)
        if len(raw.encode())>max_output: raise ProviderFailure('Fixture output budget exceeded')
        return {'response':response,'usage':{'input_tokens':None,'output_tokens':None,'cost_usd':0,
                'input_bytes':len(canonical(request).encode()),'output_bytes':len(raw.encode()),'source':'fixture-bytes'}}

class OpenAICompatible:
    mode = 'real-provider'
    def __init__(self, endpoint, model, authorized=False, token_ceiling=0, cost_ceiling=0,
                 input_rate=0,output_rate=0, transport=None):
        import math
        if type(authorized) is not bool or type(token_ceiling) is not int or not 0<=token_ceiling<=10000000:
            raise ValueError('Provider authorization/token ceiling')
        if type(cost_ceiling) not in (int,float) or not math.isfinite(cost_ceiling) or not 0<=cost_ceiling<=1000:
            raise ValueError('Provider cost ceiling')
        for rate in (input_rate,output_rate):
            if type(rate) not in (int,float) or not math.isfinite(rate) or not 0<=rate<=10000: raise ValueError('Price bound')
        if authorized and (input_rate<=0 or output_rate<=0): raise ValueError('Explicit positive prices required for runtime authorization')
        if not isinstance(model,str) or not 1<=len(model)<=128: raise ValueError('Model identifier')
        self.endpoint=endpoint
        self.model=model
        self.authorized=authorized
        self.token_ceiling=token_ceiling
        self.cost_ceiling=cost_ceiling
        self.input_rate=input_rate
        self.output_rate=output_rate
        self.transport=transport
        self.mode='fixture' if transport is not None else 'real-provider'
        self.identity={'provider':'openai-compatible-fixture-transport' if transport is not None else 'openai-compatible','model':model,'endpoint':endpoint,'temperature':0,'tokenizer':'provider-reported',
                       'http_policy':'no-redirects-v1' if transport is None else None,
                       'prices_usd_per_million':{'input':input_rate,'output':output_rate},
                       'authorized':authorized,'authorized_ceilings':{'tokens':token_ceiling,'cost_usd':cost_ceiling}}
        u=urllib.parse.urlparse(endpoint)
        if u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1')): raise ValueError('HTTPS or local HTTP required')
        if u.username or u.password or u.query or u.fragment: raise ValueError('Endpoint cannot contain credentials/query')
    def respond(self,request,max_output,timeout):
        if not self.authorized or self.token_ceiling<=0 or self.cost_ceiling<=0:
            raise ProviderUnavailable('Real-provider runtime NOT RUN: explicit authorization and positive ceilings required')
        body={'model':self.model,'temperature':0,'max_tokens':min(max_output,4096),'response_format':{'type':'json_object'},
              'seed':request.get('seed',42),'messages':[{'role':'system','content':'Return JSON with calls (write/read/python) or critique. No markdown. Never edit beyond the active frontier.'},
                          {'role':'user','content':canonical(request)}]}
        if self.mode=='real-provider':
            reserve=len(canonical(request).encode())+8192+min(max_output,4096)
            cost=(len(canonical(request).encode())+8192)*self.input_rate/1000000+min(max_output,4096)*self.output_rate/1000000
            if reserve>self.token_ceiling or cost>self.cost_ceiling:raise ProviderUnavailable('Request exceeds authorized provider ceilings')
        try:
            with request_deadline(timeout):
                if self.transport: data=self.transport(body,timeout)
                else:
                    headers={'Content-Type':'application/json'}
                    token=os.environ.get('PHIBENCH_API_KEY')
                    if token: headers['Authorization']='Bearer '+token
                    req=urllib.request.Request(self.endpoint,canonical(body).encode(),headers)
                    with http_open(req,timeout=timeout) as r:
                        raw=r.read(1048577)
                        if len(raw)>1048576: raise ProviderFailure('Response size limit')
                        data=json.loads(raw)
                usage=data['usage']
                a,b=usage['prompt_tokens'],usage['completion_tokens']
                if type(a) is not int or type(b) is not int or min(a,b)<0: raise ProviderFailure('Unusable provider token accounting')
                response=json.loads(data['choices'][0]['message']['content'])
                return {'response':response,'usage':{'input_tokens':None if self.transport else a,'output_tokens':None if self.transport else b,
                        'fixture_reported_input':a if self.transport else None,'fixture_reported_output':b if self.transport else None,
                        'input_bytes':len(canonical(request).encode()),'output_bytes':len(canonical(response).encode()),
                        'cost_usd':0 if self.transport else (a*self.input_rate+b*self.output_rate)/1000000,'source':'fixture-transport-numbers' if self.transport else 'provider-reported-tokens/configured-price'}}
        except (ProviderFailure,ProviderUnavailable,TimeoutError,InterruptedError): raise
        except Exception:
            # Raw errors may contain request headers/credentials; never archive them.
            raise ProviderFailure('Provider request or response failed; usage unknown') from None
