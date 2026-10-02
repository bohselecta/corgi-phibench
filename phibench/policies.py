"""Versioned policy contract: next -> observe -> stop; no policy affects scoring."""
from dataclasses import dataclass, asdict
import re

@dataclass(frozen=True)
class Method:
    name: str
    version: int = 1
    growth: str = 'fixed'
    step_size: int = 5
    rollback: bool = True
    failure: str = 'retry'
    memory: str = 'full'
    max_failures: int = 5
    critique: bool = False

    def validate(self):
        if not isinstance(self.name,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',self.name): raise ValueError('Method name')
        if type(self.version) is not int or self.version != 1: raise ValueError('Method version')
        if self.growth not in ('fibonacci','fixed','exponential','all'): raise ValueError('Growth')
        if self.failure not in ('retry','fibonacci','halve'): raise ValueError('Failure law')
        if self.memory not in ('two','full','fresh'): raise ValueError('Memory')
        for value, limit in [(self.step_size,64),(self.max_failures,32)]:
            if type(value) is not int or not 1 <= value <= limit: raise ValueError('Method bound')
        if type(self.rollback) is not bool or type(self.critique) is not bool: raise ValueError('Boolean required')
        return self

BUILTINS = {
    'phishell': Method('phishell',growth='fibonacci',failure='fibonacci',memory='two'),
    'fixed-step': Method('fixed-step'),
    'ralph-fresh': Method('ralph-fresh',step_size=2,memory='fresh'),
    'eval-opt': Method('eval-opt',step_size=4,critique=True,max_failures=6),
    'unrestricted': Method('unrestricted',growth='all',rollback=False),
    'exponential': Method('exponential',growth='exponential',failure='halve',memory='two'),
}

def load_method(text):
    # Deliberately bounded YAML 1.2 scalar mapping subset; no implicit evaluation.
    if not isinstance(text,str) or len(text.encode()) > 16384: raise ValueError('MDL size')
    data = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'): continue
        match = re.fullmatch(r'([a-z_]+):[ ]+([a-z][a-z0-9-]*|[0-9]+|true|false)[ ]*',line)
        if not match: raise ValueError('MDL supports only flat scalar mappings')
        key, value = match.groups()
        if key in data: raise ValueError('Duplicate MDL key')
        data[key] = int(value) if value.isdecimal() else {'true':True,'false':False}.get(value,value)
    if set(data) - set(Method.__dataclass_fields__): raise ValueError('Unknown MDL field')
    return Method(**data).validate()

class Policy:
    def __init__(self, method, obligations):
        self.method = method.validate()
        self.obligations = obligations
        self.verified = []
        self.history = []
        self.frontier = []
        self.pending = []
        self.index = 0
        self.failures = 0
        self.fib = [1,1]
        self.progress = []

    def next(self):
        if self.frontier: return self.frontier[:]
        remaining = [x for x in self.obligations if x not in self.verified]
        m = self.method
        if self.pending: size = self.pending.pop(0)
        elif m.growth == 'fibonacci':
            while len(self.fib) <= self.index: self.fib.append(self.fib[-1]+self.fib[-2])
            size = self.fib[self.index]
        elif m.growth == 'exponential': size = min(64,2**min(self.index,6))
        elif m.growth == 'all': size = len(remaining)
        else: size = m.step_size
        self.frontier = remaining[:size]
        return self.frontier[:]

    def observe(self, passed):
        targets = self.frontier[:]
        success = all(x in passed for x in self.verified + targets)
        self.history.append({'targets':targets,'success':success,'passed':passed[:]})
        self.progress.append({'step':len(self.history),'success':success,'verified':passed[:]})
        if success:
            self.verified += [x for x in targets if x not in self.verified]
            self.frontier = []
            self.index += 1
            self.failures = 0
        else:
            self.failures += 1
            size = len(targets)
            left = size
            if self.method.failure == 'halve': left = max(1,size//2)
            elif self.method.failure == 'fibonacci' and size>1:
                fib = [1,1]
                while fib[-1]<size: fib.append(fib[-1]+fib[-2])
                left = fib[-2] if fib[-1]==size else (size+1)//2
            if left<size: self.pending.insert(0,size-left)
            self.frontier = targets[:left]
        return success

    def memory(self):
        if self.method.memory == 'fresh': return {'progress':self.progress[-16:]}
        history = self.history[-2:] if self.method.memory == 'two' else self.history
        return {'history':history}

    def stop(self):
        if len(self.verified)==len(self.obligations): return 'goal_covered'
        if self.failures>=self.method.max_failures: return 'max_failures'
        return None

    def state(self):
        return {'method':asdict(self.method),'verified':self.verified[:], 'frontier':self.frontier[:], 'index':self.index,'pending':self.pending[:],'failures':self.failures}
