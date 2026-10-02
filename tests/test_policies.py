import dataclasses
import unittest
from phibench.policies import BUILTINS,Policy,load_method
from phibench.tasks import TASKS
from phibench.runner import Budget

class Policies(unittest.TestCase):
    def sequence(self,name):
        p=Policy(BUILTINS[name],[str(i) for i in range(60)]);sizes=[]
        for _ in range(5):
            frontier=p.next();sizes.append(len(frontier));p.observe(p.verified+frontier)
        return sizes
    def test_growth_laws(self):
        self.assertEqual(self.sequence('phishell'),[1,1,2,3,5])
        self.assertEqual(self.sequence('exponential'),[1,2,4,8,16])
        self.assertEqual(self.sequence('fixed-step'),[5]*5)
        self.assertEqual(self.sequence('ralph-fresh'),[2]*5)
    def test_fibonacci_failure_queues_remainder(self):
        p=Policy(BUILTINS['phishell'],[str(i) for i in range(60)])
        for _ in range(6):f=p.next();p.observe(p.verified+f)
        self.assertEqual(len(p.next()),13)
        p.observe([]);self.assertEqual(len(p.next()),8);self.assertEqual(p.pending,[5])
        p.observe(p.verified+p.next());self.assertEqual(len(p.next()),5)
    def test_regression_blocks_promotion(self):
        p=Policy(BUILTINS['phishell'],['a','b']);p.next();p.observe(['a']);p.next()
        self.assertFalse(p.observe(['b']));self.assertEqual(p.verified,['a'])
    def test_fresh_context_and_two_window(self):
        for name in ['phishell','ralph-fresh']:
            p=Policy(BUILTINS[name],[str(i) for i in range(30)])
            for _ in range(3):p.next();p.observe([])
            memory=p.memory()
            if name=='phishell':self.assertEqual(len(memory['history']),2)
            else:self.assertNotIn('history',memory);self.assertIn('progress',memory)
    def test_mdl_roundtrip_and_execution(self):
        m=load_method('name: custom\nversion: 1\ngrowth: exponential\nfailure: halve\nstep_size: 3\nrollback: false\nmemory: two\nmax_failures: 4\ncritique: false\n')
        p=Policy(m,list('abcdef'));self.assertEqual(p.next(),['a']);p.observe(['a']);self.assertEqual(p.next(),['b','c'])
    def test_mdl_rejects_unsafe_ambiguous_unbounded(self):
        for text in ['name: a\nname: b','name: x\nstep_size: 0','name: x\nstep_size: true','name: x\ngrowth: madeup','name: !python/object','name: &a x','name: x\nunknown: 2','method:\n  name: x','name: x\nrollback: maybe','x'*16385]:
            with self.subTest(text=text[:50]),self.assertRaises((ValueError,TypeError)):load_method(text)
    def test_invalid_budgets_and_tasks(self):
        for b in [Budget(calls=0),Budget(cost_usd=float('nan')),Budget(tokens=-1),Budget(tools=True)]:
            with self.assertRaises(ValueError):b.validate()
        for t in TASKS.values():self.assertIs(t.validate(),t)
        with self.assertRaises(ValueError):dataclasses.replace(TASKS['bugfix'],partition='unknown').validate()
