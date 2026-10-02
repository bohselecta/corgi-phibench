"""New, openly documented apparatus fixtures, unrelated to source holdouts."""
from dataclasses import dataclass, asdict
from .util import digest

EVALUATION_CONSTRAINTS = {
    'version':'oracle-v4',
    'host_syntax_source_bytes':65536,
    'host_syntax_ast_nodes':4096,
    'argument_preservation_profile':'json-preservation-v1',
    'argument_preservation_scope':'When a task requires unchanged arguments, runtime telemetry alone is insufficient: source must satisfy the following host-checked grammar. Ordinary functional-output checks do not require this grammar.',
    'argument_preservation_grammar':'One undecorated function with positional arguments and no defaults/annotations. Plain local-name assignments, for/if, return, break/continue/pass, JSON literals, comparisons, boolean/arithmetic expressions, indexing/slicing and len are allowed; len must retain its builtin binding. The only mutation allowed is append on a fresh local empty list assigned once and never rebound. No imports, comprehensions, nested functions, globals, introspection, other calls, or attribute/subscript assignment. Unsupported syntax fails preservation criteria even if semantically pure.',
}

@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    goal: str
    initial: dict
    public: tuple
    hidden: tuple
    partition: str = 'demonstration'
    version: int = 1

    def validate(self):
        import re
        from .util import MAX_FILE,MAX_TREE,MAX_FILES
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',self.id) or self.kind not in ('bug-fix','feature','refactor'): raise ValueError('Task identity')
        if self.partition not in ('demonstration','discovery','calibration','holdout') or type(self.version) is not int or self.version<1: raise ValueError('Task partition/version')
        if not isinstance(self.goal,str) or len(self.goal.encode())>16384: raise ValueError('Task goal')
        if 'solution.py' not in self.initial or len(self.initial)>MAX_FILES: raise ValueError('Task files')
        size=0
        for name,content in self.initial.items():
            from pathlib import PurePosixPath
            p=PurePosixPath(name)
            if not p.parts or '\x00' in name or p.is_absolute() or '..' in p.parts or '.git' in p.parts or '\\' in name or len(p.parts)>16: raise ValueError('Task path')
            if not isinstance(content,str) or len(content.encode())>MAX_FILE: raise ValueError('Task file content')
            size+=len(content.encode())
        if size>MAX_TREE or not 1<=len(self.public)<=64 or len(self.hidden)>64: raise ValueError('Task bound')
        paths=set(self.initial)
        for name in paths:
            parts=__import__('pathlib').PurePosixPath(name).parts
            if str(__import__('pathlib').PurePosixPath(name))!=name:raise ValueError('Task path must be canonical')
            if any('/'.join(parts[:i]) in paths for i in range(1,len(parts))):raise ValueError('Task file/directory conflict')
        ids=[]
        for c in self.public+self.hidden:
            if not isinstance(c,dict) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',c.get('id','')): raise ValueError('Criterion id')
            if not isinstance(c.get('description'),str) or len(c['description'])>2048:raise ValueError('Criterion description')
            ids.append(c['id'])
            if 'unchanged_args' in c and type(c['unchanged_args']) is not bool:raise ValueError('Argument preservation flag')
            if c.get('structural'):
                if c['id']!='shared' or self.kind!='refactor': raise ValueError('Structural criterion')
            elif not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,63}',c.get('function','')) or not isinstance(c.get('args'),list) or 'expected' not in c:
                raise ValueError('Criterion function/arguments/oracle')
        from .util import canonical
        if len(set(ids))!=len(ids) or len(canonical(asdict(self)).encode())>MAX_FILE: raise ValueError('Task criterion bound')
        return self

    def fingerprint(self): return digest({'definition':asdict(self),'builder_view':self.view()})
    def view(self):
        return {'id':self.id,'kind':self.kind,'goal':self.goal,'initial':self.initial,
                'obligations':[{'id':x['id'],'description':x['description']} for x in self.public],
                'version':self.version,'partition':self.partition,'view_contract':'task-view-v2',
                'evaluation_constraints':dict(EVALUATION_CONSTRAINTS)}

def case(id,description,func,args,expected,unchanged=False):
    result= {'id':id,'description':description,'function':func,'args':args,'expected':expected}
    if unchanged:result['unchanged_args']=True
    return result

BUG = Task('bugfix','bug-fix','Repair clamp(value, low, high). Reject inverted bounds with ValueError; return a bounded numeric value.',
    {'solution.py':'def clamp(value, low, high):\n    return min(value, low)\n'},
    tuple([case('inside','Keep an in-range value','clamp',[3,1,5],3),case('below','Clamp below lower bound','clamp',[-1,0,5],0),
           case('above','Clamp above upper bound','clamp',[9,0,5],5),case('equal','Equal bounds are valid','clamp',[9,2,2],2),
           case('invalid','Reject inverted bounds','clamp',[0,3,1],{'raises':'ValueError'})]),
    tuple([case('h1','negative range','clamp',[-9,-4,-1],-4),case('h2','fraction','clamp',[.5,0,1],.5)]))
FEATURE = Task('feature','feature','Implement stable_unique(items): preserve order, compare by equality, support unhashable lists, do not mutate input.',
    {'solution.py':'def stable_unique(items):\n    raise NotImplementedError\n'},
    tuple([case('empty','Empty list','stable_unique',[[]],[]),case('single','One element','stable_unique',[[1]],[1]),
           case('duplicate','Remove duplicates','stable_unique',[[1,1,2]],[1,2]),case('order','Preserve first occurrence order','stable_unique',[[3,1,3,2]],[3,1,2]),
           case('unhashable','Unhashable elements','stable_unique',[[[1],[1],[2]]],[[1],[2]])]),
    tuple([case('h1','equal mixed types','stable_unique',[[True,1,False,0]],[True,False],unchanged=True),case('h2','empty nested','stable_unique',[[[],[],[1],[]]],[[],[1]],unchanged=True)]))
REFACTOR = Task('refactor','refactor','Extract duplicated normalize logic into normalize_name(value), then use it in greet and farewell. Preserve behavior.',
    {'solution.py':'def greet(value):\n    name = " ".join(value.strip().split()).title()\n    return "Hello, " + name\n\ndef farewell(value):\n    name = " ".join(value.strip().split()).title()\n    return "Bye, " + name\n'},
    tuple([case('hello','Greeting behavior','greet',['  aDA   loVELACE '],'Hello, Ada Lovelace'),
           case('bye','Farewell behavior','farewell',[' GRACE hopper '],'Bye, Grace Hopper'),
           case('helper','Shared normalization helper','normalize_name',['  john   DOE '],'John Doe'),
           case('empty','Empty name','greet',[''],'Hello, '),
           {'id':'shared','description':'Both functions call normalize_name without duplicate split/strip/title','structural':True}]),
    tuple([case('h1','unicode','farewell',['  álICE  '],'Bye, Álice'),case('h2','whitespace','normalize_name',['x\ty\nz'],'X Y Z')]))
TASKS = {x.id:x for x in (BUG,FEATURE,REFACTOR)}
