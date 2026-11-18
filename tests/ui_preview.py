"""Read-only UI preview with invented data. Never imports the app or reads data/.env.

Run: .venv/Scripts/python tests/ui_preview.py
Only explicitly allowed static assets are served; mutations and external connections
are blocked. This is a preview harness, not a production server.
"""
import argparse
import json
from copy import deepcopy
from datetime import date
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
    'wealth-broker-realized-feed-controller.js',
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


# Opt-in, in-memory broker screens. No app imports, storage or network clients.
BROKER_NAMES = {
    'toss-wts': '토스증권', 'kis': '한국투자증권', 'nh': 'NH투자증권',
    'kiwoom': '키움증권', 'kb': 'KB증권',
}
BROKER_STATUS_PATHS = {
    '/api/toss-wts/status': 'toss-wts', '/api/kis/status': 'kis',
    '/api/nh/status': 'nh', '/api/kiwoom/status': 'kiwoom', '/api/kb/status': 'kb',
}
# Exact read/preview-only allowlist. Runtime confirmation and /import stay denied.
BROKER_POST_PATHS = {
    '/api/toss-wts/realized-feed/fetch': ('toss-wts', 'realized', 'fetch'),
    '/api/toss-wts/realized-feed/import-preview': ('toss-wts', 'realized', 'preview'),
    '/api/kis/realized-feed/fetch': ('kis', 'realized', 'fetch'),
    '/api/kis/realized-feed/import-preview': ('kis', 'realized', 'preview'),
    '/api/nh/realized-feed/fetch': ('nh', 'realized', 'fetch'),
    '/api/nh/realized-feed/import-preview': ('nh', 'realized', 'preview'),
    '/api/kiwoom/realized-feed/fetch': ('kiwoom', 'realized', 'fetch'),
    '/api/kiwoom/realized-feed/import-preview': ('kiwoom', 'realized', 'preview'),
    '/api/kb/realized-feed/fetch': ('kb', 'realized', 'fetch'),
    '/api/kb/realized-feed/import-preview': ('kb', 'realized', 'preview'),
    '/api/toss-wts/income-feed/fetch': ('toss-wts', 'income', 'fetch'),
    '/api/toss-wts/income-feed/import-preview': ('toss-wts', 'income', 'preview'),
}
SYNTHETIC_STATUSES = ('NEW', 'ALREADY_IMPORTED', 'POSSIBLE_DUPLICATE', 'INVALID')


def broker_demo_account(broker):
    return {'id': 'SYNTHETIC-' + broker, 'broker': BROKER_NAMES[broker],
            'name': '가상 전용 계좌 SYNTHETIC-00000000',
            'account_name': '가상 전용 계좌 SYNTHETIC-00000000',
            'owner': '아빠', 'account_type': 'general', 'cash_krw': 0,
            'market_value_krw': 0}


def broker_demo_row(index, day, market, kind):
    overseas = market == 'us'
    currency = 'USD' if overseas else 'KRW'
    row = {'date': day, 'datetime': day + 'T12:00:00+09:00',
           'name': '가상 거래 ' + SYNTHETIC_STATUSES[index],
           'code': 'DEMO-' + str(index), 'symbol': 'DEMO-' + str(index),
           'canonical_hash': 'SYNTHETIC-HASH-' + str(index),
           'market': market.upper(), 'market_type': market.upper(),
           'country': 'US' if overseas else 'KR', 'currency': currency,
           'quantity': 3, 'buy_amount': 100.25 if overseas else 100000,
           'sell_amount': 125.75 if overseas else 125000,
           'pnl': 25.5 if overseas else 25000, 'profit_rate': 25.0,
           'fee': 0, 'tax': 0, 'expenses_total': 0, 'exchange_rate': 1350,
           'display_name': '가상 배당·이자 ' + str(index), 'display_code': 'DEMO-' + str(index),
           'income_type': 'dividend' if index % 2 == 0 else 'account_interest',
           'gross_amount': 30.5 if overseas else 30000, 'tax_amount': 0,
           'net_amount': 30.5 if overseas else 30000}
    if kind == 'realized' and market == 'toss':
        row.update(market_type='KR', currency='KRW',
                   buy_amount={'krw': 100000, 'usd': 100.25},
                   sell_amount={'krw': 125000, 'usd': 125.75},
                   profit_loss={'krw': 25000, 'usd': 25.5})
    return row


class BrokerPreviewHandler(PreviewHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/dashboard':
            dashboard = deepcopy(DASHBOARD)
            dashboard['accounts'] = [broker_demo_account(b) for b in BROKER_NAMES]
            dashboard['holdings'] = []
            return self.send(dashboard)
        broker = BROKER_STATUS_PATHS.get(path)
        if broker:
            account = broker_demo_account(broker)
            source = {'source_account_key': 'SYNTHETIC-SOURCE-' + broker,
                      'source_account_label': '가상 원본 SYNTHETIC-****0000',
                      'auto_selected_account_id': account['id'],
                      'candidate_account_ids': [account['id']]}
            return self.send({'configured': True, 'has_account': True, 'adapter_ready': True,
                              'masked_account': 'SYNTHETIC-****0000', 'accounts': [source],
                              'candidate_account_ids': [account['id']], **source})
        super().do_GET()

    def do_POST(self):
        route = BROKER_POST_PATHS.get(urlsplit(self.path).path)
        if route is None:
            return super().do_POST()
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Expected JSON object')
            broker, kind, operation = route
            market = payload.get('market', 'kr')
            if market not in ('kr', 'us') or (broker == 'kb' and market != 'kr'):
                raise ValueError('Unsupported synthetic market')
            account = broker_demo_account(broker)
            if operation == 'fetch':
                day = date.fromisoformat(payload['to_date']).isoformat()
                date.fromisoformat(payload['from_date'])
                row_market = 'toss' if broker == 'toss-wts' and kind == 'realized' else market
                rows = [broker_demo_row(i, day, 'us' if kind == 'income' and i % 2 else row_market, kind)
                        for i in range(4)]
                if broker == 'kis':
                    # Fetch rows use profit_loss; preview candidates below use pnl.
                    for row in rows:
                        row['profit_loss'] = row.pop('pnl')
                        if market == 'us':
                            row['foreign_profit_loss'] = row['profit_loss']
                            row['foreign_buy_amount'] = row['buy_amount']
                            row['foreign_sell_amount'] = row['sell_amount']
                return self.send({'rows': rows, 'selection_tokens': [
                    f'SYNTHETIC-{broker}-{kind}-{i}' for i in range(4)],
                    'requested': {k: payload[k] for k in ('from_date', 'to_date', 'profit_rate_basis') if k in payload},
                    'market': market, 'state': 'ok', 'fetched_at': day + 'T12:00:00+09:00'})
            if payload.get('account_id') != account['id']:
                raise ValueError('Choose the synthetic destination account')
            selected = payload.get('selected_items')
            if not isinstance(selected, list) or not 1 <= len(selected) <= 4:
                raise ValueError('Select one to four synthetic rows')
            items, seen = [], set()
            counts = {'new': 0, 'already_imported': 0, 'possible_duplicate': 0, 'invalid': 0}
            for index, selection in enumerate(selected):
                if not isinstance(selection, dict):
                    raise ValueError('Expected synthetic selection')
                token = selection['selection_token']
                matches = [i for i in range(4) if token == f'SYNTHETIC-{broker}-{kind}-{i}']
                if len(matches) != 1 or token in seen:
                    raise ValueError('Synthetic selection tokens only')
                seen.add(token)
                fixture_index = matches[0]
                day = date.fromisoformat(selection['row']['date']).isoformat()
                preview_market = market
                if broker == 'toss-wts' and (payload.get('profit_rate_basis') == 'USD' or (kind == 'income' and fixture_index % 2)):
                    preview_market = 'us'
                row = broker_demo_row(fixture_index, day, preview_market, kind)
                status = SYNTHETIC_STATUSES[fixture_index]
                counts[status.lower()] += 1
                item = {'index': index, 'status': status, 'candidate': row,
                        'message': '가상 분류 결과 · 저장 불가'}
                if kind == 'realized':
                    choice = selection.get('wealth_import') or {}
                    if not isinstance(choice, dict):
                        raise ValueError('Expected synthetic display options')
                    fee = choice.get('ipo_subscription_fee_krw', 0)
                    if isinstance(fee, bool) or not isinstance(fee, (int, float)) or not 0 <= fee <= 1000000:
                        raise ValueError('Invalid synthetic fee')
                    item['wealth_import'] = {
                        'stock_type': 'ipo' if choice.get('stock_type') == 'ipo' else 'general',
                        'ipo_subscription_fee_krw': fee,
                        'provider_realized_pnl': row['pnl'], 'final_wealth_pnl': row['pnl'],
                        'memo': '가상 표시 확인용 · 금융 계산 검증 아님'}
                items.append(item)
            self.send({'items': items, 'counts': counts, 'destination_account': account,
                       'preview_ticket': f'SYNTHETIC-NOT-COMMITTABLE-{broker}-{kind}'})
        except (ValueError, KeyError, TypeError, IndexError):
            self.send({'detail': {'message': 'Invalid synthetic preview request'}}, status=400)

    # Never inherit a future write exception through a POST alias.
    do_PUT = PreviewHandler.do_POST
    do_DELETE = PreviewHandler.do_POST
    do_PATCH = PreviewHandler.do_POST


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker-synthetic', action='store_true', help='Enable invented broker read/preview responses only')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port == 4829:
        parser.error('Use an unprivileged preview port other than the Desktop port 4829')
    handler = BrokerPreviewHandler if args.broker_synthetic else PreviewHandler
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Synthetic read-only preview: http://127.0.0.1:{args.port} (broker={args.broker_synthetic})', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('Preview stopped; no data saved.', flush=True)
