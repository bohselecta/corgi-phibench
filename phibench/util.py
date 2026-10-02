import hashlib
import json
import os
from pathlib import Path

MAX_FILE = 1024 * 1024
MAX_TREE = 4 * MAX_FILE
MAX_FILES = 128

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf8') as f:
        f.write(canonical(value) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def safe_path(root, name, create=False):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Invalid path')
    p = Path(name)
    if p.is_absolute() or any(x in ('..', '.git') for x in p.parts) or len(p.parts) > 16:
        raise ValueError('Relative, unprotected path required')
    root = Path(root).resolve(strict=True)
    target = root / p
    if target == root: raise ValueError('File path required')
    for component in [*target.parents, target]:
        if component == root: continue
        if root in component.parents and component.is_symlink(): raise ValueError('Symlink forbidden')
    target.resolve().relative_to(root)
    if create: target.parent.mkdir(parents=True, exist_ok=True)
    return target

def read_file(root, name):
    p = safe_path(root, name)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size > MAX_FILE: raise ValueError('Regular file <= 1 MiB required')
        return os.read(fd, MAX_FILE + 1).decode('utf8')
    finally: os.close(fd)

def write_file(root, name, content):
    if not isinstance(content, str) or len(content.encode()) > MAX_FILE: raise ValueError('UTF-8 write <= 1 MiB required')
    p = safe_path(root, name, True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        import stat
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('Regular file required')
        with os.fdopen(fd, 'w', closefd=False, encoding='utf8') as f: f.write(content)
    finally: os.close(fd)

def snapshot(root):
    root = Path(root)
    files = {}
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        if len(Path(directory).relative_to(root).parts) > 16: raise ValueError('Directory depth limit')
        for name in dirs + names:
            p = Path(directory) / name
            if p.is_symlink(): raise ValueError('Symlink in workspace')
        if '.git' in dirs or '.git' in names: raise ValueError('Git control path in workspace')
        for name in sorted(names):
            rel = (Path(directory) / name).relative_to(root).as_posix()
            files[rel] = read_file(root, rel)
            total += len(files[rel].encode())
            if total > MAX_TREE or len(files) > MAX_FILES: raise ValueError('Workspace quota exceeded')
    return dict(sorted(files.items()))

def restore(root, files):
    import shutil
    for p in Path(root).iterdir():
        if p.is_dir() and not p.is_symlink(): shutil.rmtree(p)
        else: p.unlink()
    for name, content in files.items(): write_file(root, name, content)
