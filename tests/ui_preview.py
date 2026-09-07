"""Read-only UI preview with invented data. Never imports the app or reads data/.env.

Run: .venv/Scripts/python tests/ui_preview.py
Only explicitly allowed static assets are served; mutations and external connections
are blocked. This is a preview harness, not a production server.
"""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
ALLOWED = {"index.html", "wealth.js", "wealth.css", "wealth-overrides.css",
           "wealth-layout.js", "wealth-layout.css", "icon-192.png", "apple-touch-icon.png"}
DASHBOARD = {
    "summary": {"total_value_krw": 85000000, "total_stock_value_krw": 80000000,
                "total_cash_krw": 5000000, "account_count": 0},
    "accounts": [], "holdings": [], "classifications": [], "sector_classifications": [],
    "currency_summary": {}, "fx_rates": {"KRW": 1, "USD": 1350},
    "bank_accounts": [{"id": "demo-bank", "bank_name": "가상은행", "account_name": "생활비",
                       "balance": 12000000, "owner": "아빠", "currency": "KRW"}],
    "savings_accounts": [], "insurance_accounts": [],
    "loan_accounts": [{"id": "demo-loan", "loan_type": "mortgage", "owner": "아빠",
                       "product_name": "가상 주택대출", "current_balance": 120000000}],
    "real_estates": [{"id": "demo-home", "name": "가상 주거자산", "property_type": "own",
                      "current_price": 420000000, "purchase_price": 400000000, "owner": "아빠"}],
    "updated_at": "2026-09-08T12:00:00+09:00",
}


class PreviewHandler(BaseHTTPRequestHandler):
    def send(self, payload, content_type="application/json; charset=utf-8", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode())

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/api/'):
            responses = {
                '/api/auth/me': {'username': 'DEMO', 'role': 'user', 'must_change_password': False},
                '/api/dashboard': DASHBOARD,
                '/api/family-members': {'members': ['아빠', '엄마', '자녀']},
                '/api/asset-records': {'records': []},
                '/api/market-overview': {'items': []},
                '/api/ledger': {'year': 2026, 'month': 9, 'owner': '모두', 'transactions': [],
                                'total_income': 0, 'total_expense': 0, 'net_savings': 0, 'savings_rate': 0},
                '/api/ledger/cards': [],
                '/api/dividends': {'holdings': [], 'monthly': []},
                '/api/actual-dividends': {'records': [], 'monthly': [], 'available_years': []},
                '/api/realized-pnl': {'records': [], 'monthly': [], 'available_years': []},
            }
            self.send(responses.get(path, {}))
            return
        name = 'index.html' if path == '/' else path.removeprefix('/static/')
        if name not in ALLOWED:
            self.send({'detail': 'Preview asset not allowed'}, status=404)
            return
        content = (STATIC / name).read_bytes()
        if name == 'index.html':
            content = content.replace(b'<body>', '<body><div style="padding:8px;text-align:center;background:#274c46;color:#fff;font-size:12px">가상 데이터 미리보기 · 실제 계좌와 연결되지 않음 · 저장 불가</div>'.encode())
        self.send(content, (mimetypes.guess_type(name)[0] or 'application/octet-stream') + '; charset=utf-8')

    def do_POST(self):
        self.send({'detail': '가상 미리보기에서는 저장하지 않습니다.'}, status=403)

    do_PUT = do_DELETE = do_POST

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    print('Synthetic read-only preview: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), PreviewHandler).serve_forever()
