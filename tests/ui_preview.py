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
ALLOWED = {"wealth-asset-category-state.js", "wealth-color-picker.js", "wealth-color-picker.css", "index.html", "wealth.js", "wealth-dialog-system.css", "wealth-ui-density.css", "wealth-transaction-defaults.js", "wealth-savings-contributions.js", "wealth-savings-contributions.css", "wealth.css", "wealth-overrides.css",
           "wealth-layout.js", "wealth-layout.css", "wealth-invest-tab-state.js", "wealth-settings-surface.js", "wealth-settings.js", "wealth-automation-status.js", "wealth-planning.js", "wealth-planning-model.js", "icon-192.png", "apple-touch-icon.png"}
ALLOWED.update({"wealth-national-pension.js", "wealth-national-pension.css", "wealth-pension-import.js"})
ALLOWED.update({'wealth-ledger-ocr.js', 'wealth-ledger-ocr.css'})
# Explicit assets used by the current Desktop bundle and its lazy loaders.
ALLOWED.update({
    'fonts/pretendard/1.3.9/pretendardvariable.css',
    'fonts/pretendard/1.3.9/woff2/PretendardVariable.woff2',
    'fonts/tossface/37720aa5/TossFaceFontMac-09.woff2',
    'wealth-account-reorder.css',
    'wealth-account-reorder.js',
    'wealth-accountinfo-import.js',
    'wealth-accountinfo-owner-options.js',
    'wealth-account-section-summary.js',
    'wealth-calendar.js',
    'wealth-color-preferences.css',
    'wealth-color-preferences.js',
    'wealth-dividend-source.js',
    'wealth-family-financial-income-allocation.css',
    'wealth-family-financial-income-allocation.js',
    'wealth-family-financial-income-risk.css',
    'wealth-family-financial-income-risk.js',
    'wealth-family-view.js',
    'wealth-financial-income-what-if.css',
    'wealth-financial-income-what-if.js',
    'wealth-format.js',
    'wealth-heatmap-view.js',
    'wealth-income-period-broker-filter.js',
    'wealth-ipo-event-months.js',
    'wealth-ipo.js',
    'wealth-ledger-period-filter.js',
    'wealth-ledger-timeseries-history.js',
    'wealth-money-input.js',
    'wealth-operation-feedback.js',
    'wealth-real-estate-view.js',
    'wealth-ledger-transactions-view.js',
    'wealth-stock-autocomplete.js',
    'wealth-ipo-schedule-card-view.js',
    'wealth-dashboard-owner-model.js',
    'wealth-holding-account-options-view.js',
    'wealth-holding-dialog-controller.js',
    'wealth-tax-accounts-view.js',
    'wealth-securities-accounts-view.js',
    'wealth-broker-import-preview-model.js',
    'wealth-broker-import-preview-screen-controller.js',
    'wealth-ipo-historical-preview-view.js',
    'wealth-dividend-summary-view.js',
    'wealth-sector-view.js',
    'wealth-holdings-row-view.js',
    'wealth-asset-records-screen-controller.js',
    'wealth-admin-users-view.js',
    'wealth-investment-summary-view.js',
    'wealth-account-yearly-view.js',
    'wealth-donut-chart.js',
    'wealth-ledger-screen-controller.js',
    'wealth-income-month-navigation.js',
    'wealth-insurance-form-model.js',
    'wealth-holding-signals.js',
    'wealth-broker-ui.js',
    'wealth-market-card-preferences.js',
    'wealth-market-view.js',
    'wealth-stock-records-view.js',
    'wealth-actual-dividend-detail-view.js',
    'wealth-heatmap-model.js',
    'wealth-bank-account-options.js',
    'wealth-savings-form-model.js',
    'wealth-loan-form-model.js',
    'wealth-savings-dialog-controller.js',
    'wealth-stock-chart-view.js',
    'wealth-ipo-applicant-api.js',
    'wealth-ipo-applicant-model.js',
    'wealth-ipo-applicant-view.js',
    'wealth-income-tabs-controller.js',
    'wealth-realized-pnl-view.js',
    'wealth-ledger-cards-view.js',
    'wealth-ledger-recurring-view.js',
    'wealth-ledger-data.js',
    'wealth-ledger-transactions-model.js',
    'wealth-stock-records-model.js',
    'wealth-banking-view.js',
    'wealth-insurance-view.js',
    'wealth-period-filter-core.js',
    'wealth-pnl-year-intent.js',
    'wealth-system-update.css',
    'wealth-system-update.js',
    'wealth-timeseries-label-layout.js',
    'wealth-timeseries-panzoom.js',
    'wealth-timeseries-period-core.js',
    'wealth-timeseries-unified.js',
    'wealth-timeseries-visible-range.js',
    'wealth-ipo-sale-bridge.js',
})
DASHBOARD = {
    "summary": {"total_value_krw": 85000000, "total_stock_value_krw": 80000000,
                "total_cash_krw": 5000000, "account_count": 2},
    "accounts": [
        {"id":"demo-stock-a", "name":"가상 성장계좌", "broker":"가상증권", "owner":"아빠", "account_type":"general", "cash_krw":3000000, "cash_usd":0, "market_value_krw":53000000},
        {"id":"demo-stock-b", "name":"가상 연금계좌", "broker":"가상증권", "owner":"엄마", "account_type":"pension", "cash_krw":2000000, "cash_usd":0, "market_value_krw":32000000},
    ],
    "holdings": [
        {"id":"demo-h-a", "account_id":"demo-stock-a", "account_name":"가상 성장계좌", "broker":"가상증권", "name":"가상 아빠 종목", "code":"DEMO-DAD", "owner":"아빠", "currency":"KRW", "quantity":500, "current_price":100000, "avg_price":90000, "market_value_krw":50000000, "cost_value_krw":45000000, "profit_krw":5000000},
        {"id":"demo-h-b", "account_id":"demo-stock-b", "account_name":"가상 연금계좌", "broker":"가상증권", "name":"가상 엄마 종목", "code":"DEMO-MOM", "owner":"엄마", "currency":"KRW", "quantity":300, "current_price":100000, "avg_price":90000, "market_value_krw":30000000, "cost_value_krw":27000000, "profit_krw":3000000},
    ], "classifications": [], "sector_classifications": [],
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
                '/api/planning': {'revision': 0, 'buckets': [], 'accounts': {}, 'holdings': {}, 'history': [
                    {'date': day, 'owner': '모두', 'assets': net + 120000000, 'debt': 120000000, 'net_worth': net}
                    for day, net in [('2026-06-08', 380000000), ('2026-07-08', 385000000), ('2026-08-08', 382000000), ('2026-09-08', 397000000)]
                ]},
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
        if name.endswith('.woff2'):
            content_type = 'font/woff2'
        elif name.endswith('.css'):
            content_type = 'text/css; charset=utf-8'
        else:
            content_type = (mimetypes.guess_type(name)[0] or 'application/octet-stream') + '; charset=utf-8'
        self.send(content, content_type)

    def do_POST(self):
        self.send({'detail': '가상 미리보기에서는 저장하지 않습니다.'}, status=403)

    do_PUT = do_DELETE = do_POST

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    print('Synthetic read-only preview: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), PreviewHandler).serve_forever()
