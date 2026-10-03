"""Evidence integrity at the export boundary, independent of the browser renderer."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from phibench.experiment import report
from phibench.laboratory import prepare_report
from phibench.receipts import ReceiptError
from phibench.util import digest
from phibench.view import render_html,export_html
ROOT=Path(__file__).resolve().parents[1]

class LaboratoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.success=report(ROOT/'examples/success-experiment')
        cls.regression=report(ROOT/'examples/regression-experiment')

    def test_reconstructs_final_status_even_when_outer_row_is_spoofed(self):
        r=copy.deepcopy(self.regression);r['rows'][0].update(status='completed',verified=99,total=99)
        actual=prepare_report(r)['rows'][0]
        self.assertEqual('failed',actual['status']);self.assertEqual((7,7),(actual['verified'],actual['total']))
        self.assertFalse(actual['complete']);self.assertTrue(actual['receipt']['artifact_complete'])

    def test_hash_and_protocol_tampering_rejected_without_overwriting_export(self):
        r=copy.deepcopy(self.success);r['rows'][0]['receipt']['events'][4]['payload']['input_bytes']=1
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'lab.html';target.write_text('retained previous export')
            with self.assertRaises(ReceiptError):export_html(r,target)
            self.assertEqual('retained previous export',target.read_text())
        r=copy.deepcopy(self.success);r['manifest']['budget']['calls']=99
        with self.assertRaisesRegex(ValueError,'manifest'):prepare_report(r)

    def test_context_measurements_must_match_serialized_request_even_with_rehashed_chain(self):
        r=copy.deepcopy(self.success);events=r['rows'][0]['receipt']['events']
        next(e for e in events if e['kind']=='model.request')['payload']['input_bytes']=1
        previous='0'*64
        for e in events:
            e['previous']=previous;e['hash']=digest({k:v for k,v in e.items() if k!='hash'});previous=e['hash']
        with self.assertRaisesRegex(ValueError,'Context measurement'):prepare_report(r)

    def test_missing_receipt_cannot_claim_success(self):
        r=copy.deepcopy(self.success);r['rows'][0]['receipt']=None
        p=prepare_report(r)['rows'][0]
        self.assertEqual('not_run',p['status']);self.assertIsNone(p['verified'])

    def test_rollback_restores_full_file_origin_and_does_not_infer_line_authorship(self):
        r=prepare_report(self.regression)['rows'][0]['receipt'];events=r['events']
        rollbacks=[e for e in events if e['kind']=='workspace.snapshot' and e['payload']['label']=='rollback']
        self.assertTrue(rollbacks)
        for rollback in rollbacks:
            prior=[e for e in events[:rollback['seq']] if e['kind']=='workspace.snapshot' and e['payload']['root']==rollback['payload']['root']][-1]
            versions={v['seq']:v['files'] for v in r['file_versions']}
            self.assertEqual(versions[prior['seq']],versions[rollback['seq']])
        origin=prepare_report(self.success)['rows'][0]['receipt']['file_versions'][-1]['files']['solution.py']
        self.assertEqual('recorded full-file write',origin['kind']);self.assertEqual(1,origin['model_call'])
        self.assertNotIn('line_authorship',origin)

    def test_untrusted_text_cannot_close_script_or_expand_template_marker(self):
        r=copy.deepcopy(self.success);r['manifest']['environment']['note']='</script><script>globalThis.pwned=true</script>__SCRIPT__'
        r['protocol']=digest(r['manifest'])
        # Changing the frozen protocol cannot inherit old run receipts.
        for row in r['rows']:row['receipt']=None
        html=render_html(r)
        self.assertNotIn('<script>globalThis.pwned',html)
        self.assertIn('\\u003c/script\\u003e',html);self.assertIn('__SCRIPT__',html)
        self.assertEqual(2,html.count('<script'))

    def test_duplicate_scheduled_runs_cannot_hide_rows(self):
        r=copy.deepcopy(self.success);r['manifest']['runs'].append(r['manifest']['runs'][0]);r['protocol']=digest(r['manifest'])
        with self.assertRaisesRegex(ValueError,'Duplicate scheduled'):prepare_report(r)
