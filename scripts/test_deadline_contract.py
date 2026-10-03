#!/usr/bin/env python3
"""Prove the deadline acceptance test rejects two injected regressions.

Mutations live only in this test process. Runtime files and assertions are unchanged.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('deadline_acceptance',root/'tests/test_runner.py')
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
from phibench.sandbox import Sandbox
method='test_sandbox_setup_shares_run_deadline_without_model_request'
real_probe=subprocess.run
real_doctor=Sandbox.doctor

def too_long(*args,**kwargs):
    kwargs['timeout']=2
    return real_probe(*args,**kwargs)
def forget_remaining(instance,workspace,timeout=None):
    return real_doctor(instance,workspace)

for name,target,mutant in [('version receives a fresh two-second quota','phibench.sandbox.subprocess.run',too_long),
        ('execution omits the remaining deadline','phibench.sandbox.Sandbox.doctor',forget_remaining)]:
    result=unittest.TestResult()
    with patch(target,new=mutant):unittest.TestSuite([tests.Runner(method)]).run(result)
    assert result.failures and not result.errors,(name,result.failures,result.errors)
    print('PASS: deadline acceptance rejects '+name)
