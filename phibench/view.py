from pathlib import Path
from .util import canonical

def export_html(report,path):
    data=canonical(report).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=Path(__file__).with_name('observatory.html').read_text()
    Path(path).write_text(template.replace('__DATA__',data),encoding='utf8')
    return Path(path)
