"""Coordinated ledger interest mirrors under the existing canonical lock order.

Exception rollback restores exact bytes while all participants remain locked.
This is not a crash-recovery journal or a filesystem multi-file atomic rename.
"""
from copy import deepcopy
from datetime import datetime
from functools import wraps
from inspect import signature
import math
import uuid

from app.services.financial_json import financial_user_locks, read_financial_json
from app.services.secure_files import atomic_write_private_bytes
from app.services.test_safety import assert_write_allowed


def interest_transaction(function):
    """Probe under ordinary locks; release before acquiring the extended set."""
    sig = signature(function)

    @wraps(function)
    def run(*args, **kwargs):
        from app.services import ledger, portfolio, dividend_records as dividends
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        username = bound.arguments.get('username')
        payload = bound.arguments.get('payload', {})
        if 'mirror_to_dividend_interest' in payload and type(payload['mirror_to_dividend_interest']) is not bool:
            raise ValueError('은행 이자 연동 여부는 boolean이어야 합니다.')
        tx_id = bound.arguments.get('tx_id') or payload.get('id')
        is_delete = function.__name__ == 'delete_transaction'
        is_add = function.__name__ == 'add_transaction'
        # No lock upgrade: an ordinary operation finishes inside the probe lock.
        with financial_user_locks(username, 'ledger.json', 'portfolio.json'):
            existing = read_financial_json(ledger.get_ledger_path(username), default=ledger.default_ledger_data())
            previous = next((t for t in existing['transactions'] if t.get('id') == tx_id), None)
            linked = bool(payload.get('mirror_to_dividend_interest') or
                          (previous or {}).get('mirror_to_dividend_interest'))
            if not linked:
                return function(*args, **kwargs)

        with financial_user_locks(username, 'ledger.json', 'portfolio.json', 'dividend_records.json'):
            paths = [ledger.get_ledger_path(username), portfolio._get_portfolio_file(username),
                     dividends._get_dividend_file(username)]
            snapshots = {}
            for path in paths:
                assert_write_allowed(path)
                if path.exists():
                    read_financial_json(path)  # Refuse corruption before touching any participant.
                    snapshots[path] = path.read_bytes()
                else:
                    snapshots[path] = None
            existing = read_financial_json(paths[0], default=ledger.default_ledger_data())
            previous = next((t for t in existing['transactions'] if t.get('id') == tx_id), None)
            effective = {**(previous or {}), **payload}
            enabled = bool(effective.get('mirror_to_dividend_interest')) and not is_delete
            if effective.get('type') != 'income':
                enabled = False
            bank = None
            if enabled:
                from app.services.transaction_preferences import owner_matches, validate_owner
                owner = effective.get('owner', '모두')
                validate_owner(owner)
                amount = float(effective.get('amount') or 0)
                if not math.isfinite(amount) or amount <= 0 or effective.get('category') != '배당/금융수익':
                    raise ValueError('은행 이자 연동은 양수 금액의 배당/금융수익 수입만 지원합니다.')
                p = read_financial_json(paths[1])
                bank = next((a for a in p.get('bank_accounts', [])
                             if a.get('id') == effective.get('account_id')), None)
                if not bank or not owner_matches(bank, owner) or str(bank.get('currency', 'KRW')).upper() != 'KRW':
                    raise ValueError('소유자 범위에 있는 KRW 은행계좌를 선택해 주세요.')
                if effective.get('card_id') or effective.get('is_card_payment'):
                    raise ValueError('카드 거래는 은행 이자로 연동할 수 없습니다.')
            if is_add and previous:
                fields = ('date', 'type', 'category', 'amount', 'owner', 'account_id', 'merchant', 'memo')
                if all(effective.get(k, '') == previous.get(k, '') for k in fields) and enabled == bool(previous.get('mirror_to_dividend_interest')):
                    return deepcopy(previous)
                raise ValueError('이미 존재하는 거래 ID입니다. 수정 요청을 사용해 주세요.')
            if not is_delete:
                tx_id = tx_id or str(uuid.uuid4())
                updated = dict(payload)
                if is_add:
                    updated['id'] = tx_id
                updated['mirror_to_dividend_interest'] = enabled
                updated['linked_interest_record_id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, f'ledger-interest:{tx_id}')) if enabled else ''
                if bank:
                    updated['account_name'] = bank.get('account_name') or bank.get('name') or '은행계좌'
                bound.arguments['payload'] = updated
            try:
                result = function(*bound.args, **bound.kwargs)
                if result is None or result is False:
                    return result
                container = read_financial_json(paths[2], default={'records': []})
                fingerprint = f'ledger-interest:{tx_id}'
                records = [r for r in container.get('records', [])
                           if not (r.get('source') == 'ledger_interest' and r.get('source_fingerprint') == fingerprint)]
                if enabled:
                    now = datetime.now().astimezone().isoformat()
                    records.append({'id': result['linked_interest_record_id'], 'date': result['date'],
                        'income_type': 'account_interest', 'amount': result['amount'], 'amount_krw': result['amount'],
                        'currency': 'KRW', 'fx_rate': 1.0, 'owner': result['owner'],
                        'account_name': result['account_name'], 'name': f"{result['account_name']} 이자",
                        'code': '', 'broker': bank.get('bank_name', ''), 'memo': result.get('memo', ''),
                        'source': 'ledger_interest', 'source_fingerprint': fingerprint,
                        'source_meta': {'ledger_transaction_id': tx_id, 'bank_account_id': result['account_id']},
                        'created_at': (next((r.get('created_at') for r in container.get('records', [])
                                            if r.get('source_fingerprint') == fingerprint), None) or now), 'updated_at': now})
                dividends.write_dividend_records(records, username)
                return result
            except Exception:
                failures = []
                for path, before in snapshots.items():
                    try:
                        if before is None:
                            path.unlink(missing_ok=True)
                        elif not path.exists() or path.read_bytes() != before:
                            atomic_write_private_bytes(path, before)
                    except Exception as exc:
                        failures.append(exc)
                if failures:
                    raise ledger.PersistenceConsistencyError('은행 이자 연동 원복 실패; 추가 거래를 중단하고 저장소를 확인해야 합니다.') from failures[0]
                raise
    return run
