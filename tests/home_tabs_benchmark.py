"""Opt-in synthetic main/candidate Chromium comparison (no production stores).

Run with PYTHONPATH=.;tests: python -m tests.home_tabs_benchmark
Baseline static files live only in an automatically removed temporary directory.
"""
from pathlib import Path
import json
import shutil
import statistics
import subprocess
import tempfile
from unittest.mock import patch
from tests.test_account_reorder_runtime import chrome_preview
from tests import test_static_transport_chrome as transport

BASE = '940a42053297059dcbafdc837458876269958086'
ROOT = Path(__file__).resolve().parents[1]


def main():
    samples=[]
    with tempfile.TemporaryDirectory(prefix='wealth-home-tabs-baseline-') as directory:
        baseline=Path(directory)/'static'
        shutil.copytree(transport.STATIC,baseline)
        for name in ['index.html','wealth-layout.js','wealth-layout.css','wealth-planning.js']:
            content=subprocess.check_output(['git','show',f'{BASE}:app/static/{name}'],cwd=ROOT)
            # Match the Windows checkout's line endings in both candidates.
            (baseline/name).write_bytes(content.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        fixture=chrome_preview.__wrapped__()
        call,evaluate,_=next(fixture)
        try:
            current=transport.STATIC
            for width in [360,1280]:
                for iteration in range(3):
                    for label in (['main','candidate'] if iteration%2==0 else ['candidate','main']):
                        with patch.object(transport,'STATIC',baseline if label=='main' else current):
                            with transport.transport_server(True) as port:
                                row=transport.measure(call,evaluate,port,width)
                        assert not row['errors'],row['errors']
                        samples.append({'variant':label,'width':width,'iteration':iteration,
                            'fcp_ms':row['fcp'],'asset_ms':row['visible'],'ready_ms':row['ready'],
                            'api_count':len(row['api']),'metrics':row['metrics']})
        finally:
            try:next(fixture)
            except StopIteration:pass
    summary=[]
    for width in [360,1280]:
        result={'width':width}
        for variant in ['main','candidate']:
            rows=[r for r in samples if r['width']==width and r['variant']==variant]
            result[variant]={key:statistics.median(r[key] for r in rows) for key in ['fcp_ms','asset_ms','ready_ms','api_count']}
        summary.append(result)
    report={'baseline':BASE,'conditions':'Chromium, synthetic loopback, gzip, cold HTTP cache, SW bypass; mobile CPU 4x/network latency 40ms/250KBps; desktop CPU 1x/20ms/500KBps; 3 alternating samples each', 'summary':summary,'samples':samples}
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
