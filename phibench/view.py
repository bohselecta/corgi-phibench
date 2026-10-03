"""Export a verified, standalone laboratory without running any candidate code."""
from pathlib import Path
import os
import tempfile
from .laboratory import prepare_report
from .util import canonical


def render_html(report):
    report = prepare_report(report)
    data = canonical(report).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    if len(data.encode()) > 32 * 1024 * 1024:
        raise ValueError('Laboratory export <=32 MiB; inspect larger experiments with CLI replay')
    template = Path(__file__).with_name('observatory.html').read_text(encoding='utf8')
    assets = Path(__file__).with_name('laboratory')
    # Substitute assets first: evidence containing a template marker stays evidence.
    return template.replace('__STYLE__',(assets/'style.css').read_text(encoding='utf8')).replace(
        '__SCRIPT__',(assets/'app.js').read_text(encoding='utf8')).replace('__DATA__',data)


def export_html(report,path):
    html = render_html(report)
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf8') as f:
            f.write(html);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return path
