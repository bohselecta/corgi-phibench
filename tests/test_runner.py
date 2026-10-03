import dataclasses
import json
from pathlib import Path
import tempfile
import unittest
from phibench.tasks import TASKS
from phibench.policies import BUILTINS
from phibench.providers import FixtureProvider,OpenAICompatible,ProviderUnavailable
from phibench.runner import run,Budget,Interrupted
from phibench.evaluator import verify_saved
from phibench.receipts import Journal,ReceiptError,read_events,replay,recover
from phibench.experiment import experiment,report
from phibench.util import canonical

class Runner(unittest.TestCase):
    def test_http_redirects_cannot_forward_authorization_or_change_endpoint(self):
        import urllib.request
        from unittest.mock import Mock,patch
        from phibench.providers import NoRedirect,http_open,ProviderFailure
        req=urllib.request.Request('https://provider.example/chat',data=b'{}',headers={'Authorization':'Bearer test-only-placeholder'})
        for code in (301,302,303,307,308):
            fp=Mock()
            with self.assertRaises(ProviderFailure):NoRedirect().redirect_request(req,fp,code,'Moved',{},'https://other.example/chat')
            fp.close.assert_called_once()
        with patch('urllib.request.build_opener') as factory:
            http_open(req,.25)
            self.assertIsInstance(factory.call_args.args[0],NoRedirect)
            factory.return_value.open.assert_called_once_with(req,timeout=.25)
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def runone(self,method='phishell',task='bugfix',scenario='success',budget=Budget(),provider=None):
        p=self.root/str(len(list(self.root.iterdir())))
        return p,run(TASKS[task],BUILTINS[method],provider or FixtureProvider(scenario),p,budget)
    def test_sandbox_setup_shares_run_deadline_without_model_request(self):
        import shutil,subprocess
        from unittest.mock import patch
        from phibench.sandbox import Sandbox
        which=shutil.which
        real_probe=subprocess.run
        real_execute=Sandbox.execute
        for phase in ['version','execution']:
            with self.subTest(phase=phase):
                shim=self.root/('slow-bwrap-'+phase)
                completed=self.root/('probe-completed-'+phase)
                delay='True' if phase=='version' else 'False'
                shim.write_text('#!/usr/bin/python3\nimport os,sys,time\n'
                    'if "--version" in sys.argv:\n'
                    ' if '+delay+':\n  time.sleep(1.4)\n  open('+repr(str(completed))+',"w").write("completed")\n'
                    ' print("bubblewrap 0.12.0")\n'
                    'else:\n time.sleep(1.4)\n open('+repr(str(completed))+',"w").write("completed")\n'
                    ' os.execv("/usr/bin/bwrap",["bwrap",*sys.argv[1:]])\n')
                shim.chmod(0o755)
                version_limits=[];execution_limits=[]
                def probe(*args,**kwargs):
                    version_limits.append(kwargs.get('timeout'))
                    return real_probe(*args,**kwargs)
                def execute(instance,*args,**kwargs):
                    execution_limits.append(kwargs.get('timeout'))
                    return real_execute(instance,*args,**kwargs)
                provider=FixtureProvider('success')
                with patch('phibench.sandbox.shutil.which',side_effect=lambda name:str(shim) if name=='bwrap' else which(name)), \
                        patch('phibench.sandbox.subprocess.run',side_effect=probe), \
                        patch.object(Sandbox,'execute',new=execute), \
                        patch.object(provider,'respond',wraps=provider.respond) as respond:
                    p,result=self.runone(provider=provider,budget=Budget(wall_seconds=1))
                    respond.assert_not_called()
                # Inspect the enforced limits, not scheduler/receipt-cleanup latency.
                self.assertTrue(version_limits)
                self.assertTrue(all(v is not None and 0<v<1 for v in version_limits))
                if phase=='execution':
                    self.assertTrue(execution_limits)
                    self.assertTrue(all(v is not None and 0<v<1 for v in execution_limits))
                self.assertFalse(completed.exists(),'Slow probe completed beyond the shared deadline')
                self.assertEqual(result['status'],'timeout')
                self.assertEqual(result['model_calls'],0)
                self.assertFalse(any(event['kind']=='model.request' for event in read_events(p/'events.jsonl')))
    def test_all_policies_all_task_classes_real_process_checks(self):
        for task in TASKS:
            for method in BUILTINS:
                with self.subTest(task=task,method=method):
                    p,r=self.runone(method,task)
                    self.assertEqual(r['status'],'completed');self.assertEqual(r['verified'],7)
                    self.assertIsNone(r['usage']['input_tokens']);self.assertEqual(r['usage']['cost_usd'],0)
                    self.assertEqual(verify_saved(p,TASKS[task])['status'],'PASS')
    def test_null_failure_retained_and_zero_not_missing(self):
        p,r=self.runone(scenario='null')
        self.assertEqual(r['status'],'failed');self.assertEqual(r['verified'],1);self.assertFalse(r['complete'])
        self.assertEqual(verify_saved(p,TASKS['bugfix'])['status'],'PASS')
    def test_crash_timeout_and_partial_usage_unknown(self):
        for scenario,status in [('crash','crashed'),('timeout','timeout')]:
            p,r=self.runone(scenario=scenario)
            self.assertEqual(r['status'],status);self.assertEqual(r['model_calls'],1)
            self.assertIsNone(r['complete']);self.assertEqual(r['events'][-1]['kind'],'run.finished')
            self.assertEqual(r['usage']['cost_usd'],0)
    def test_call_and_tool_budget_before_extra_action(self):
        p,r=self.runone(budget=Budget(calls=1))
        self.assertEqual(r['status'],'budget_exhausted');self.assertEqual(r['model_calls'],1)
        p,r=self.runone(budget=Budget(tools=1))
        self.assertEqual(r['status'],'budget_exhausted');self.assertEqual(r['tool_calls'],1)
    def test_rollback_retains_last_green_and_replay_all_snapshots(self):
        p,r=self.runone(scenario='regression')
        self.assertEqual(r['status'],'failed');self.assertFalse(r['complete']);self.assertTrue(r['artifact_complete'])
        self.assertTrue(any(s['label']=='rollback' for s in r['snapshots']))
        self.assertEqual(verify_saved(p,TASKS['bugfix'])['status'],'PASS')
    def test_critic_calls_do_not_write_and_critique_enters_context(self):
        p,r=self.runone(method='eval-opt',scenario='null')
        requests=r['contexts'];self.assertIn('critique',[x['phase'] for x in requests])
        optimize=[x for x in requests if x['phase']=='optimize']
        self.assertTrue(optimize);self.assertIn('Check public feedback',optimize[0]['request']['critique'])
        self.assertEqual(r['tool_calls'],0)
    def test_unavailable_provider_calls_no_transport(self):
        touched=[]
        provider=OpenAICompatible('https://example.invalid/chat','model')
        from unittest.mock import patch
        with patch('phibench.providers.http_open') as network:
            p,r=self.runone(provider=provider)
            network.assert_not_called()
        self.assertEqual(r['status'],'unavailable');self.assertEqual(r['usage']['cost_usd'],0);self.assertEqual(r['model_calls'],0)
    def test_fixture_transport_provider_accounting(self):
        def transport(body,timeout):
            self.assertIn('max_tokens',body)
            return {'usage':{'prompt_tokens':17,'completion_tokens':19},'choices':[{'message':{'content':'{"calls":[]}'}}]}
        p=OpenAICompatible('https://example.invalid/chat','model',True,100000,1,1,1,transport)
        r=p.respond({'x':1},100,1)
        self.assertIsNone(r['usage']['input_tokens']);self.assertIsNone(r['usage']['output_tokens']);self.assertEqual(r['usage']['fixture_reported_input'],17);self.assertEqual(r['usage']['fixture_reported_output'],19)
        self.assertEqual(p.mode,'fixture');self.assertEqual(r['usage']['source'],'fixture-transport-numbers');self.assertEqual(r['usage']['cost_usd'],0)
    def test_smaller_provider_authorization_refuses_dispatch(self):
        from unittest.mock import patch
        for tokens,cost in ((1,1),(100000,.000001)):
            p=OpenAICompatible('https://example.invalid/chat','model',True,tokens,cost,1,1)
            with patch('phibench.providers.http_open') as network:
                _,r=self.runone(provider=p,budget=Budget(tokens=100000,cost_usd=1))
                network.assert_not_called()
            self.assertEqual(r['status'],'budget_exhausted');self.assertEqual(r['model_calls'],0)
    def test_provider_total_deadline_and_signal_restoration(self):
        import signal,time
        old=signal.getsignal(signal.SIGALRM)
        def transport(*args):time.sleep(2)
        p=OpenAICompatible('https://example.invalid/chat','model',True,100000,1,1,1,transport)
        started=time.monotonic()
        with self.assertRaises(TimeoutError):p.respond({},100,.1)
        self.assertLess(time.monotonic()-started,.8)
        self.assertEqual(signal.getsignal(signal.SIGALRM),old);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
    def test_provider_deadline_refuses_active_alarm_and_worker_thread(self):
        import signal,threading
        p=OpenAICompatible('https://example.invalid/chat','model',True,100000,1,1,1,lambda *args:None)
        signal.setitimer(signal.ITIMER_REAL,10)
        try:
            with self.assertRaises(ProviderUnavailable):p.respond({},100,1)
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],9)
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        errors=[]
        def worker():
            try:p.respond({},100,1)
            except ProviderUnavailable:errors.append(True)
        t=threading.Thread(target=worker);t.start();t.join(2)
        self.assertEqual(errors,[True])
    def test_provider_prices_and_authorization_change_fingerprint(self):
        from phibench.util import digest
        a=OpenAICompatible('https://example.invalid/chat','model',True,100000,1,1,1)
        b=OpenAICompatible('https://example.invalid/chat','model',True,100000,1,2,1)
        c=OpenAICompatible('https://example.invalid/chat','model',True,200000,1,1,1)
        self.assertNotEqual(digest(a.identity),digest(b.identity));self.assertNotEqual(digest(a.identity),digest(c.identity))
    def test_workspace_initialization_failure_retains_receipt(self):
        from unittest.mock import patch
        with patch('phibench.runner.restore',side_effect=OSError('synthetic storage failure')):
            p,r=self.runone()
        self.assertEqual(r['status'],'crashed')
        self.assertEqual(r['events'][0]['kind'],'run.started');self.assertEqual(r['events'][-1]['kind'],'run.finished')
    def test_interrupt_finalizes_complete_partial_record(self):
        class Interrupting(FixtureProvider):
            def respond(self,*args):raise Interrupted('synthetic interruption')
        p,r=self.runone(provider=Interrupting())
        self.assertEqual(r['status'],'interrupted');self.assertTrue(r['snapshots'])
    def test_frozen_matrix_reports_missing_and_rejects_mismatch(self):
        class Interrupting(FixtureProvider):
            def respond(self,*args):raise Interrupted()
        result=experiment(self.root/'matrix',provider=Interrupting())
        self.assertEqual(len(result['rows']),18)
        self.assertEqual(sum(r['status']=='not_run' for r in result['rows']),17)
        m=self.root/'matrix'/'experiment.json';data=json.loads(m.read_text());data['manifest']['seeds']=[99];m.write_text(canonical(data))
        with self.assertRaises(ValueError):report(self.root/'matrix')

class Receipts(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_tamper_is_detected(self):
        with Journal(self.root) as j:j.append('run.started',{'mode':'fixture'})
        p=self.root/'events.jsonl';s=p.read_text().replace('fixture','real-provider');p.write_text(s)
        with self.assertRaises(ReceiptError):read_events(p)
    def test_lock_and_torn_tail_recovery_preserves_bytes(self):
        with Journal(self.root) as j:
            j.append('run.started',{'mode':'fixture'})
            with self.assertRaises(ReceiptError):recover(self.root)
        with (self.root/'events.jsonl').open('ab') as f:f.write(b'{"unfinished":')
        with self.assertRaises(ReceiptError):replay(self.root)
        r=recover(self.root);self.assertEqual(r['status'],'interrupted')
        self.assertEqual((self.root/'torn-tail.bin').read_bytes(),b'{"unfinished":')
        self.assertEqual(recover(self.root)['root'],r['root'])
        with self.assertRaises(ReceiptError):Journal(self.root)
    def test_recovery_counts_pending_tool_attempt(self):
        with Journal(self.root) as j:
            j.append('run.started',{'mode':'fixture'})
            j.append('tool.request',{'call':1,'request':{'tool':'write'}})
        r=recover(self.root)
        self.assertEqual(r['tool_calls'],1);self.assertEqual(r['pending_tool_calls'],[1])
        self.assertEqual(r['status'],'interrupted');self.assertIsNone(r['complete'])
    def test_tool_results_require_matching_attempts(self):
        with Journal(self.root) as j:
            j.append('run.started',{'mode':'fixture'})
            j.append('tool.result',{'call':1,'result':{}})
        with self.assertRaises(ReceiptError):replay(self.root)
    def test_cost_estimate_is_recomputed_from_retained_prices(self):
        with Journal(self.root) as j:
            j.append('run.started',{'mode':'real-provider','provider':{'prices_usd_per_million':{'input':2,'output':3}}})
            j.append('model.request',{'call':1})
            j.append('model.response',{'call':1,'usage':{'input_tokens':5,'output_tokens':7,'cost_usd':.01}})
        with self.assertRaises(ReceiptError):replay(self.root)

class CustomTask(unittest.TestCase):
    def test_invalid_initial_paths_fail_before_creating_receipt(self):
        for files in ({'solution.py':'pass\n','solution.py/child':'x'}, {'solution.py':'pass\n','x/./y':'x'}):
            task=dataclasses.replace(TASKS['bugfix'],initial=files)
            with tempfile.TemporaryDirectory() as d:
                dest=Path(d)/'run'
                with self.assertRaises(ValueError):run(task,BUILTINS['phishell'],FixtureProvider(),dest)
                self.assertFalse(dest.exists())
    def test_custom_task_and_script_are_versioned_fixtures(self):
        from phibench.tasks import Task
        task=Task('answer-task','feature','Return 42.',{'solution.py':'def answer():raise NotImplementedError\n'},
                  ({'id':'answer','description':'Return 42','function':'answer','args':[],'expected':42},),(),partition='discovery')
        script={'calls':[{'tool':'write','path':'solution.py','content':'def answer():return 42\n'}]}
        provider=FixtureProvider(script=script)
        with tempfile.TemporaryDirectory() as d:
            r=run(task,BUILTINS['phishell'],provider,Path(d)/'run')
            self.assertEqual(r['status'],'completed');self.assertEqual(r['run']['task']['partition'],'discovery')
            self.assertIn('script_hash',r['run']['provider']);self.assertIsNone(r['usage']['input_tokens'])
            self.assertEqual(verify_saved(Path(d)/'run',task)['status'],'PASS')
