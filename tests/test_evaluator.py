from pathlib import Path
import tempfile
import unittest
from phibench.evaluator import evaluate,preservation_proven
from phibench.tasks import TASKS
from phibench.sandbox import Sandbox
from phibench.util import write_file

class Oracle(unittest.TestCase):
    def test_constraints_are_equal_visible_and_versioned_without_hidden_answers(self):
        import dataclasses
        from phibench.tasks import EVALUATION_CONSTRAINTS
        views=[task.view() for task in TASKS.values()]
        self.assertTrue(all(v['evaluation_constraints']==EVALUATION_CONSTRAINTS for v in views))
        self.assertTrue(all(v['view_contract']=='task-view-v2' for v in views))
        task=TASKS['feature'];without_hidden=dataclasses.replace(task,hidden=())
        self.assertEqual(task.view(),without_hidden.view())
        self.assertNotEqual(task.fingerprint(),without_hidden.fingerprint())
        self.assertNotIn('hidden',task.view());self.assertNotIn('expected',str(task.view()))
        self.assertIn('No imports, comprehensions',task.view()['evaluation_constraints']['argument_preservation_grammar'])
        from unittest.mock import patch
        with patch.dict(EVALUATION_CONSTRAINTS,{'argument_preservation_profile':'changed-profile'}):
            changed=task.fingerprint()
        self.assertNotEqual(task.fingerprint(),changed)
    def test_host_proof_is_bounded_and_shared_between_criteria(self):
        from phibench.tasks import Task
        from unittest.mock import patch
        source='def stable_unique(items):\n result=[]\n'+' result.append(1)\n'*1000+' return result\n'
        self.assertFalse(preservation_proven(source,'stable_unique'))
        self.assertFalse(preservation_proven(' '*65537,'stable_unique'))
        source='def stable_unique(items):\n result=[]\n for item in items:\n  if item not in result:result.append(item)\n return result\n'
        criteria=tuple({'id':f'check{i}','description':'Preserve','function':'stable_unique','args':[[1,1,2]],'expected':[1,2],'unchanged_args':True} for i in range(12))
        task=Task('shared-proof','feature','Preserve input',{'solution.py':source},criteria,()).validate()
        with tempfile.TemporaryDirectory() as d:
            write_file(d,'solution.py',source)
            with patch('phibench.evaluator.preservation_proven',wraps=preservation_proven) as proof:
                self.assertTrue(evaluate(task,d,Sandbox(),timeout=1)['complete'])
                self.assertEqual(proof.call_count,1)
    def test_frame_serializer_spoof_cannot_authorize_preservation(self):
        from phibench.tasks import Task
        source='''import sys, json
def stable_unique(items):
 result=[]
 for item in items:
  if item not in result:result.append(item)
 parent=sys._getframe(1)
 original=parent.f_locals['original']
 items.clear()
 real=json.dumps
 json.dumps=lambda value,*a,**k:original if value is parent.f_locals['request']['args'] else real(value,*a,**k)
 return result
'''
        criterion={'id':'unique','description':'Preserve input','function':'stable_unique','args':[[1,1,2]],'expected':[1,2],'unchanged_args':True}
        task=Task('spoof-check','feature','Do not mutate input.',{'solution.py':''},(criterion,),()).validate()
        with tempfile.TemporaryDirectory() as d:
            write_file(d,'solution.py',source)
            r=evaluate(task,d,Sandbox(),hidden=True)
            self.assertFalse(r['complete'])
            self.assertFalse(r['results'][0]['passed'])
    def test_preservation_proof_rejects_alias_rebinding_and_nested_mutation(self):
        for source in (
            'def stable_unique(items):\n result=[]\n result=items\n result.append(1)\n return result\n',
            'def stable_unique(items):\n result=[]\n for result in items:result.append(1)\n return items\n',
            'def stable_unique(items):\n items[0].append(1)\n return items\n',
            'def stable_unique(items):\n result=[]\n result.append(items.pop())\n return result\n',
            'def stable_unique(items):\n return [x for x in items]\n',
        ):
            with self.subTest(source=source):self.assertFalse(preservation_proven(source,'stable_unique'))
        self.assertTrue(preservation_proven('def stable_unique(items):\n result=[]\n for item in items:\n  if item not in result:result.append(item)\n return result\n','stable_unique'))
    def test_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            write_file(d,'solution.py','def stable_unique(items):\n result=[]\n while items:\n  item=items.pop(0)\n  if item not in result:result.append(item)\n return result\n')
            r=evaluate(TASKS['feature'],d,Sandbox(),hidden=True)
            self.assertEqual(len(r['passed']),5)
            self.assertFalse(r['complete']);self.assertTrue(all(not x['passed'] for x in r['results'] if x['hidden']))
    def test_printed_pass_cannot_spoof_host_oracle(self):
        with tempfile.TemporaryDirectory() as d:
            write_file(d,'solution.py','print("PASS")\ndef clamp(*args):return 0\n')
            r=evaluate(TASKS['bugfix'],d,Sandbox(),hidden=True)
            self.assertFalse(r['complete']);self.assertEqual(r['passed'],[])
