"""Local synthetic planning save/reload harness. No real data, env or finance APIs.

Run from repository root: python tests/planning_ui_preview.py
Only planning writes are enabled, to a disposable TemporaryDirectory.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import planning, portfolio
from ui_preview import PreviewHandler, DASHBOARD


class PlanningPreview(PreviewHandler):
    def do_GET(self):
        if urlsplit(self.path).path == '/api/planning':
            return self.send(planning.read_planning('DEMO'))
        super().do_GET()

    def send(self, payload, content_type='application/json; charset=utf-8', status=200):
        if isinstance(payload, bytes) and 'text/html' in content_type:
            payload = payload.replace('저장 불가'.encode(), '테스트 저장만 가능 · 종료 시 폐기'.encode())
        super().send(payload, content_type, status)

    def do_POST(self):
        path = urlsplit(self.path).path
        if not path.startswith('/api/planning/'):
            return super().do_POST()
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            self.send(planning.mutate('DEMO', path.rsplit('/', 1)[1], payload))
        except planning.PlanningConflict as error:
            self.send({'detail': str(error)}, status=409)
        except (ValueError, KeyError, TypeError) as error:
            self.send({'detail': str(error)}, status=400)


if __name__ == '__main__':
    with TemporaryDirectory(prefix='wealth-planning-ui-') as directory:
        with patch.object(portfolio, '_get_portfolio_file', return_value=Path(directory) / 'portfolio.json'):
            fixture = deepcopy(portfolio.EMPTY_PORTFOLIO)
            fixture['accounts'] = deepcopy(DASHBOARD['accounts'])
            fixture['holdings'] = deepcopy(DASHBOARD['holdings'])
            portfolio.write_portfolio(fixture, 'DEMO')
            print('Disposable planning preview: http://127.0.0.1:8766', flush=True)
            ThreadingHTTPServer(('127.0.0.1', 8766), PlanningPreview).serve_forever()
