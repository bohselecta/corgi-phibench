import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from phibench.util import read_file,write_file,snapshot
from phibench.sandbox import Sandbox,SandboxUnavailable

class SandboxRequirements(unittest.TestCase):
    def test_old_or_unrecognized_bubblewrap_fails_closed(self):
        for output in ['bubblewrap 0.6.1\n','bubblewrap 0.9.0\n','bubblewrap 0.11.0\n','unrecognized\n']:
            with patch('phibench.sandbox.subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')):
                with self.assertRaises(SandboxUnavailable):Sandbox()
    def test_unavailable_or_timed_out_version_probe_fails_closed(self):
        for error in [FileNotFoundError(),subprocess.CalledProcessError(1,'bwrap')]:
            with patch('phibench.sandbox.subprocess.run',side_effect=error):
                with self.assertRaises(SandboxUnavailable):Sandbox()
        with patch('phibench.sandbox.subprocess.run',side_effect=subprocess.TimeoutExpired('bwrap',2)):
            with self.assertRaises(TimeoutError):Sandbox()

class FileBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'work';self.root.mkdir()
    def tearDown(self):self.temp.cleanup()
    def test_sibling_prefix_and_absolute(self):
        sibling=self.root.with_name('work-copy');sibling.mkdir()
        for p in ['../work-copy/escape',str(self.root/'escape'),'.git/config','x/../../escape']:
            with self.assertRaises(ValueError):write_file(self.root,p,'x')
        self.assertFalse((sibling/'escape').exists())
    def test_symlinks_and_fifo(self):
        other=Path(self.temp.name)/'secret';other.write_text('SECRET')
        (self.root/'link').symlink_to(other)
        for fn in [lambda:read_file(self.root,'link'),lambda:write_file(self.root,'link','overwrite')]:
            with self.assertRaises(ValueError):fn()
        (self.root/'dirlink').symlink_to(other.parent,target_is_directory=True)
        with self.assertRaises(ValueError):write_file(self.root,'dirlink/x','escape')
        os.mkfifo(self.root/'fifo')
        with self.assertRaises(ValueError):read_file(self.root,'fifo')
        self.assertEqual(other.read_text(),'SECRET')
    def test_nested_utf8_and_quota(self):
        write_file(self.root,'nested/file','π');self.assertEqual(read_file(self.root,'nested/file'),'π')
        with self.assertRaises(ValueError):write_file(self.root,'large','x'*1048577)
    def test_symlink_tree_rejected(self):
        (self.root/'escape').symlink_to('/etc')
        with self.assertRaises(ValueError):snapshot(self.root)

class Isolation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.s=Sandbox(timeout=.4)
        write_file(self.root,'solution.py','x=1\n')
    def tearDown(self):self.temp.cleanup()
    def execute(self,code):return self.s.execute(self.root,code)
    def test_doctor(self):self.assertEqual(self.s.doctor(self.root)['status'],'PASS')
    def test_host_and_judge_paths_hidden_environment_stripped(self):
        os.environ['PHIBENCH_TEST_SECRET']='sentinel-never-in-child'
        secret=self.root.parent/'phibench-secret-boundary'
        secret.write_text('sentinel')
        try:
            r=self.execute('import os;print(dict(os.environ));print(os.path.exists("'+str(secret)+'"));print(os.path.exists("/workspace"));print(os.getuid())')
            self.assertEqual(r['exit_code'],0);self.assertNotIn('sentinel',r['stdout']);self.assertIn('False\nFalse\n65534',r['stdout'])
        finally:secret.unlink();os.environ.pop('PHIBENCH_TEST_SECRET')
    def test_workspace_readonly(self):
        r=self.execute('open("solution.py","w").write("malicious")')
        self.assertNotEqual(r['exit_code'],0);self.assertEqual(read_file(self.root,'solution.py'),'x=1\n')
    def test_fork_exec_child_and_threads_denied(self):
        for code in ['import os; os.fork()','import subprocess; subprocess.run(["/bin/true"])','import threading;threading.Thread(target=lambda:None).start()']:
            self.assertNotEqual(self.execute(code)['exit_code'],0)
    def test_network_denied(self):
        r=self.execute('import socket;s=socket.socket();s.settimeout(.1);s.connect(("1.1.1.1",443))')
        self.assertNotEqual(r['exit_code'],0)
    def test_memory_timeout_and_output_bounds(self):
        self.assertNotEqual(self.execute('x=bytearray(512*1024*1024)')['exit_code'],0)
        self.assertEqual(self.execute('while True: pass')['reason'],'timeout')
        r=self.execute('import os;os.close(1);os.close(2)\nwhile True:pass')
        self.assertEqual(r['reason'],'timeout');self.assertLess(r['duration_ms'],800)
        r=self.execute('import os\nwhile True: os.write(1,b"x"*8192)')
        self.assertEqual(r['reason'],'output_limit');self.assertLessEqual(len(r['stdout']),1048576+8192)
    def test_scratch_quota(self):
        r=self.execute('import os\nfor i in range(20):\n f=open("/tmp/"+str(i),"wb"); f.write(b"x"*1048576); f.close()')
        self.assertNotEqual(r['exit_code'],0)
