"""Linux execution: fail closed; never fall back to a host process."""
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time

class SandboxUnavailable(RuntimeError): pass

class Sandbox:
    version = 'bubblewrap-python-ro-v1'
    def __init__(self, timeout=3):
        if not 0 < timeout <= 30: raise ValueError('Timeout range')
        self.timeout = timeout
        self.bwrap = shutil.which('bwrap')
        self.prlimit = shutil.which('prlimit')
        if not self.bwrap or not self.prlimit or not Path('/usr/bin/python3').is_file():
            raise SandboxUnavailable('Linux Bubblewrap, prlimit and /usr/bin/python3 required')

    def command(self, workspace, code):
        if not isinstance(code,str) or len(code.encode())>65536: raise ValueError('Python command <= 64 KiB required')
        args = [self.prlimit,'--as=268435456','--cpu=3','--nofile=64','--fsize=1048576','--core=0','--',
                self.bwrap,'--unshare-all','--die-with-parent','--uid','65534','--gid','65534','--cap-drop','ALL',
                '--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/tmp','--setenv','LANG','C.UTF-8',
                '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin']
        for p in ['/lib','/lib64']: 
            if Path(p).exists(): args += ['--ro-bind',p,p]
        args += ['--proc','/proc','--dev','/dev','--size','8388608','--tmpfs','/tmp',
                 '--ro-bind',str(Path(workspace).resolve()),'/work','--chdir','/work',
                 '--','/usr/bin/python3','-I','-B','-c',code]
        return args

    def execute(self, workspace, code, input_data=b'', timeout=None):
        import tempfile
        if len(input_data)>1048576: raise ValueError('Input bound')
        limit = min(self.timeout, timeout) if timeout is not None else self.timeout
        if limit <= 0: return {'exit_code':124,'stdout':'','stderr':'','reason':'timeout','duration_ms':0}
        started = time.monotonic()
        chunks = {1:bytearray(),2:bytearray()}
        reason = 'exited'
        # Spooling input avoids blocking on an untrusted process that never reads stdin.
        with tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as seccomp:
            incoming.write(input_data); incoming.seek(0)
            seccomp.write(process_filter()); seccomp.seek(0)
            argv=self.command(workspace,code)
            position=argv.index('--',argv.index(self.bwrap)+1)
            argv[position:position]=['--seccomp',str(seccomp.fileno())]
            proc = subprocess.Popen(argv,pass_fds=(seccomp.fileno(),),stdin=incoming,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},start_new_session=True)
            sel = selectors.DefaultSelector()
            for number, stream in [(1,proc.stdout),(2,proc.stderr)]:
                os.set_blocking(stream.fileno(),False)
                sel.register(stream,selectors.EVENT_READ,number)
            try:
                while sel.get_map() or proc.poll() is None:
                    if time.monotonic()-started>limit:
                        reason = 'timeout'; break
                    for key,_ in sel.select(min(.05,max(.001,limit-(time.monotonic()-started)))):
                        data = os.read(key.fileobj.fileno(),8192)
                        if not data: sel.unregister(key.fileobj); continue
                        chunks[key.data].extend(data)
                        if sum(map(len,chunks.values()))>1048576:
                            reason = 'output_limit'; break
                    if reason != 'exited': break
                if reason != 'exited' and proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL)
                proc.wait(timeout=1)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid,signal.SIGKILL); proc.wait()
                sel.close(); proc.stdout.close(); proc.stderr.close()
        return {'exit_code':proc.returncode if reason=='exited' else 124,
                'stdout':bytes(chunks[1]).decode('utf8',errors='replace'),
                'stderr':bytes(chunks[2]).decode('utf8',errors='replace'),
                'reason':reason,'duration_ms':round((time.monotonic()-started)*1000)}

    def doctor(self, workspace):
        result = self.execute(workspace,'print("PHIBENCH_ISOLATED")')
        if result['exit_code'] or result['stdout'].strip() != 'PHIBENCH_ISOLATED':
            raise SandboxUnavailable('Bubblewrap namespace execution unavailable; no host fallback')
        return {'sandbox':self.version,'status':'PASS','limits':{'memory_bytes':268435456,'processes':1,
                'cpu_seconds':3,'scratch_bytes':8388608,'file_bytes':1048576,'output_bytes':1048576}}


def process_filter():
    import platform, struct
    # Classic seccomp BPF: verify ABI, reject x32, deny every child-creation syscall.
    machine=platform.machine()
    if machine=='x86_64': arch=0xc000003e; banned=[56,57,58,435]
    elif machine=='aarch64': arch=0xc00000b7; banned=[220,435]
    else: raise SandboxUnavailable('Unsupported seccomp ABI')
    instructions=[(0x20,0,0,4),(0x15,1,0,arch),(0x06,0,0,0x80000000),
                  (0x20,0,0,0),(0x35,0,1,0x40000000),(0x06,0,0,0x80000000)]
    for nr in banned: instructions.extend([(0x15,0,1,nr),(0x06,0,0,0x00050001)])
    instructions.append((0x06,0,0,0x7fff0000))
    return b''.join(struct.pack('<HBBI',*i) for i in instructions)
