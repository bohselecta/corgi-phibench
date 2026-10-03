#!/usr/bin/env python3
"""One explicit apparatus fixture: fail a two-obligation frontier, then repair it.

The provider knows the answer. This illustrates controller mechanics, not model ability.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phibench.experiment import experiment
from phibench.policies import BUILTINS
from phibench.providers import FixtureProvider,SOLUTIONS
from phibench.util import canonical
from phibench.tasks import TASKS

class SplitFixture(FixtureProvider):
    def __init__(self):
        super().__init__()
        self.identity={'provider':'deterministic-mechanism-fixture','model':'split-on-step-3-v1',
                       'scenario':'one-deliberate-regression','tokenizer':None}
    def respond(self,request,max_output,timeout):
        content='raise RuntimeError("deliberate step-3 regression")\n' if request['step']==3 else SOLUTIONS[request['task']['id']]
        response={'calls':[{'tool':'write','path':'solution.py','content':content}]}
        raw=canonical(response)
        if len(raw.encode())>max_output:raise ValueError('Fixture output budget')
        return {'response':response,'usage':{'input_tokens':None,'output_tokens':None,'cost_usd':0,
                'input_bytes':len(canonical(request).encode()),'output_bytes':len(raw.encode()),'source':'fixture-bytes'}}

if __name__=='__main__':
    value=experiment(Path(sys.argv[1]),methods=[BUILTINS['phishell']],tasks=[TASKS['bugfix']],provider=SplitFixture())
    row=value['rows'][0]
    assert row['status']=='completed' and row['verified']==row['total']==7
    failures=[e for e in row['receipt']['events'] if e['kind']=='policy.observation' and not e['payload']['success']]
    assert len(failures)==1 and failures[0]['payload']['state']['pending']==[1]
    print('PASS: observed 2 -> 1 + queued 1, rollback, repair, and independent final checks; deterministic fixture only.')
