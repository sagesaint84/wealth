"""Failure and concurrency evidence using only disposable synthetic storage."""
from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import asset_records, dividend_records, ledger, pnl_records, portfolio, savings
from app.services import financial_json as storage
from app.services import secure_files
from regression_support import empty_portfolio, import_main_without_loading_real_env


@pytest.fixture
def users(tmp_path, monkeypatch):
    def directory(username=None):
        path = tmp_path / (username or "default")
        path.mkdir(parents=True, exist_ok=True)
        return path
    monkeypatch.setattr("app.services.user_manager.get_user_data_dir", directory)
    monkeypatch.setattr(ledger, "get_user_data_dir", directory)
    return directory


@pytest.mark.parametrize("failure", ["serialize", "temp_write", "flush", "fsync", "replace"])
def test_failure_preserves_previous_bytes_and_cleans_unique_temp(tmp_path, monkeypatch, failure):
    target = tmp_path / "portfolio.json"
    old = b'{"accounts": [], "holdings": [], "settings": {}, "marker": "previous"}'
    target.write_bytes(old)
    value = empty_portfolio(marker="next")
    if failure == "serialize":
        value["unserializable"] = object()
    elif failure == "temp_write":
        def fail_write(value, stream, **kwargs):
            stream.write('{"partial":')
            raise OSError("synthetic temp write failure")
        monkeypatch.setattr(secure_files.json, "dump", fail_write)
    elif failure == "flush":
        original = secure_files.os.fdopen
        class FailingFlush:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def write(self, value): return self.stream.write(value)
            def flush(self): raise OSError("synthetic flush failure")
            def fileno(self): return self.stream.fileno()
        monkeypatch.setattr(secure_files.os, "fdopen", lambda *a, **k: FailingFlush(original(*a, **k)))
    else:
        def fail(*args): raise OSError("synthetic failure")
        monkeypatch.setattr(secure_files.os, failure if failure == "fsync" else "replace", fail)
    with pytest.raises((TypeError, OSError)):
        storage.write_financial_json(target, value)
    assert target.read_bytes() == old
    assert json.loads(target.read_bytes())["marker"] == "previous"
    assert list(tmp_path.glob("*.tmp")) == []


def test_temp_creation_failure_preserves_previous_bytes(tmp_path, monkeypatch):
    target = tmp_path / "portfolio.json"
    storage.write_financial_json(target, empty_portfolio())
    before = target.read_bytes()
    def fail(**kwargs): raise OSError("synthetic temp creation failure")
    monkeypatch.setattr(secure_files.tempfile, "mkstemp", fail)
    with pytest.raises(OSError): storage.write_financial_json(target, empty_portfolio(marker="new"))
    assert target.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_stream_owned_descriptor_is_not_closed_twice_on_failure(tmp_path, monkeypatch):
    close = MagicMock(wraps=os.close)
    monkeypatch.setattr(secure_files.os, "close", close)
    with pytest.raises(TypeError):
        secure_files.atomic_write_private_json(tmp_path / "portfolio.json", {"bad": object()})
    # The file context already closed the descriptor. A later os.close(fd)
    # could close an unrelated descriptor that another thread has reused.
    close.assert_not_called()
    assert list(tmp_path.glob("*.tmp")) == []


def test_fdopen_failure_closes_still_unowned_descriptor(tmp_path, monkeypatch):
    close = MagicMock(wraps=os.close)
    monkeypatch.setattr(secure_files.os, "close", close)
    def fail(*args, **kwargs): raise OSError("synthetic fdopen failure")
    monkeypatch.setattr(secure_files.os, "fdopen", fail)
    with pytest.raises(OSError):
        secure_files.atomic_write_private_json(tmp_path / "portfolio.json", {})
    close.assert_called_once()
    assert list(tmp_path.glob("*.tmp")) == []


FAMILIES = [
    ("portfolio.json", lambda: portfolio.read_portfolio("alice"),
     lambda: portfolio.write_portfolio(empty_portfolio(), "alice")),
    ("asset_records.json", lambda: asset_records.read_asset_records("alice"),
     lambda: asset_records.write_asset_records({"records": []}, "alice")),
    ("ledger.json", lambda: ledger.read_ledger("alice"),
     lambda: ledger.write_ledger(ledger.default_ledger_data(), "alice")),
    ("dividend_records.json", lambda: dividend_records.read_dividend_records("alice"),
     lambda: dividend_records.write_dividend_records([], "alice")),
    ("realized_pnl_records.json", lambda: pnl_records.read_pnl_records("alice"),
     lambda: pnl_records.write_pnl_records([], "alice")),
]


@pytest.mark.parametrize("filename,reader,writer", FAMILIES)
@pytest.mark.parametrize("broken", [b'{"truncated":', b"null", b'{"records":"invalid", "accounts":"invalid", "transactions":"invalid"}'])
def test_corrupt_authoritative_never_bootstraps_or_overwrites(users, filename, reader, writer, broken):
    target = users("alice") / filename
    target.write_bytes(broken)
    with pytest.raises(RuntimeError): reader()
    with pytest.raises(RuntimeError): writer()
    assert target.read_bytes() == broken
    assert list(target.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("filename,reader,writer", FAMILIES)
def test_missing_bootstrap_remains_supported(users, filename, reader, writer):
    assert not (users("alice") / filename).exists()
    reader()
    assert (users("alice") / filename).exists()
    writer()
    assert json.loads((users("alice") / filename).read_text(encoding="utf-8"))


def test_new_user_legacy_empty_templates_still_load(users):
    from app.services.user_manager import init_empty_portfolio
    init_empty_portfolio(users("new"))
    assert portfolio.read_portfolio("new")["accounts"] == []
    assert asset_records.read_asset_records("new")["records"] == []
    assert dividend_records.read_dividend_records("new") == []
    assert pnl_records.read_pnl_records("new") == []


def test_readonly_existing_documents_do_not_create_lock_files(users):
    directory = users("alice")
    for filename, value in (
        ("portfolio.json", empty_portfolio()),
        ("asset_records.json", {"records": []}),
        ("ledger.json", ledger.default_ledger_data()),
        ("dividend_records.json", {"records": []}),
        ("realized_pnl_records.json", {"records": []}),
    ):
        (directory / filename).write_text(json.dumps(value), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    for _, reader, _ in FAMILIES: reader()
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    assert list(directory.glob("*.lock")) == []


def test_path_aliases_and_recursive_writes_share_one_domain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "portfolio.json"
    relative = Path("child") / ".." / "portfolio.json"
    assert storage.canonical_path(relative) == storage.canonical_path(path)
    if os.name == "nt":
        assert storage.canonical_path(Path(str(path).upper())) == storage.canonical_path(path)
    with storage.financial_lock(relative):
        storage.write_financial_json(path, empty_portfolio())
        with storage.financial_lock(path):
            storage.write_financial_json(relative, empty_portfolio(marker="nested"))
    assert storage.read_financial_json(path)["marker"] == "nested"
    assert len(list(tmp_path.glob("*.lock"))) == 1


def _contended_services(monkeypatch, read_module, read_name, first, second):
    """Pause the first actual canonical read, prove the other attempts its lock."""
    entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
    original_read = getattr(read_module, read_name)
    original_lock = storage.financial_lock
    reads = []
    def read(*args, **kwargs):
        value = original_read(*args, **kwargs)
        reads.append(threading.current_thread().name)
        if len(reads) == 1:
            entered.set()
            assert release.wait(5)
        return value
    @contextmanager
    def observed_lock(path, **kwargs):
        if threading.current_thread().name == "second-financial-writer": attempted.set()
        with original_lock(path, **kwargs): yield
    monkeypatch.setattr(read_module, read_name, read)
    monkeypatch.setattr(storage, "financial_lock", observed_lock)
    errors = []
    def run(operation):
        try: operation()
        except Exception as exc: errors.append(exc)
    a = threading.Thread(target=run, args=(first,), name="first-financial-writer")
    b = threading.Thread(target=run, args=(second,), name="second-financial-writer")
    a.start()
    try:
        assert entered.wait(5)
        b.start()
        assert attempted.wait(5)
        assert len(reads) == 1  # second cannot read the old state
    finally:
        release.set()
        a.join(5)
        if b.ident is not None: b.join(5)
    assert not a.is_alive() and not b.is_alive()
    assert errors == []
    assert len(reads) == 2


def test_same_portfolio_rmw_preserve_two_updates(users, monkeypatch):
    portfolio.write_portfolio(empty_portfolio(accounts=[{"id": "account", "name": "synthetic"}]), "alice")
    _contended_services(monkeypatch, savings, "read_portfolio",
        lambda: savings.save_bank_account({"name": "bank", "balance": 10}, "alice"),
        lambda: savings.save_bank_account({"name": "second bank", "balance": 20}, "alice"))
    data = portfolio.read_portfolio("alice")
    assert len(data["bank_accounts"]) == 2
    assert sum(x["balance"] for x in data["bank_accounts"]) == 30


def test_different_modules_same_canonical_path_preserve_both_updates(users, monkeypatch):
    portfolio.write_portfolio(empty_portfolio(accounts=[{"id": "account"}]), "alice")
    entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
    original = portfolio.read_portfolio
    original_lock = storage.financial_lock
    reads = []
    def read(*args, **kwargs):
        value = original(*args, **kwargs)
        reads.append(threading.current_thread().name)
        if threading.current_thread().name == "bank":
            entered.set()
            assert release.wait(5)
        return value
    @contextmanager
    def observed(path, **kwargs):
        if threading.current_thread().name == "family": attempted.set()
        with original_lock(path, **kwargs): yield
    monkeypatch.setattr(savings, "read_portfolio", read)
    monkeypatch.setattr(portfolio, "read_portfolio", read)
    monkeypatch.setattr(storage, "financial_lock", observed)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(lambda: (setattr(threading.current_thread(), "name", "bank"),
                                    savings.save_bank_account({"name": "bank", "balance": 10}, "alice")))
        assert entered.wait(5)
        second = pool.submit(lambda: (setattr(threading.current_thread(), "name", "family"),
                                     portfolio.migrate_add_family_group("alice")))
        try:
            assert attempted.wait(5)
            assert reads == ["bank"]
        finally: release.set()
        first.result(timeout=5); second.result(timeout=5)
    data = original("alice")
    assert data["accounts"][0]["family_group"] == "All"
    assert len(data["bank_accounts"]) == 1


@pytest.mark.parametrize("family", ["stock", "ledger", "dividend", "pnl"])
def test_record_rmw_preserves_two_appends(users, monkeypatch, family):
    if family == "stock":
        mod, name = asset_records, "read_asset_records"
        make = lambda label: asset_records.upsert_asset_record({"date": "2026-10-09", "memo": label}, username="alice")
        final = lambda: asset_records.read_asset_records("alice")["records"]
    elif family == "ledger":
        mod, name = ledger, "read_ledger"
        make = lambda label: ledger.add_transaction({"date": "2026-10-09", "type": "income", "amount": 10, "memo": label}, "alice")
        final = lambda: ledger.read_ledger("alice")["transactions"]
    else:
        mod = dividend_records if family == "dividend" else pnl_records
        name = "read_dividend_records" if family == "dividend" else "read_pnl_records"
        create = mod.create_dividend_record if family == "dividend" else mod.create_pnl_record
        make = lambda label: create({"date": "2026-10-09", "code": "SYNTH", "name": "synthetic", "memo": label}, "alice")
        final = lambda: getattr(mod, name)("alice")
        monkeypatch.setattr(mod, "resolve_stock_info", lambda code, name, currency: (code, name, currency))
    _contended_services(monkeypatch, mod, name, lambda: make("A"), lambda: make("B"))
    assert {x["memo"] for x in final()} == {"A", "B"}


def test_different_user_and_file_do_not_wait_for_held_portfolio(users):
    completed = threading.Event()
    with storage.financial_lock(users("alice") / "portfolio.json"):
        def isolated_writes():
            portfolio.write_portfolio(empty_portfolio(), "bob")
            asset_records.upsert_asset_record({"date": "2026-10-09"}, username="alice")
            completed.set()
        worker = threading.Thread(target=isolated_writes)
        worker.start()
        assert completed.wait(5)
    worker.join(5)
    assert not worker.is_alive()


def _process_append(path, label, attempted, entered=None, release=None):
    # Child processes receive only a synthetic absolute target; no user settings.
    attempted.set()
    with storage.financial_lock(Path(path)):
        data = storage.read_financial_json(Path(path))
        if entered is not None:
            entered.set()
            assert release.wait(10)
        data["updates"].append(label)
        storage.write_financial_json(Path(path), data)


def test_cross_process_rmw_preserves_two_updates(tmp_path):
    target = tmp_path / "portfolio.json"
    storage.write_financial_json(target, empty_portfolio(updates=[]))
    ctx = multiprocessing.get_context("spawn")
    entered, release = ctx.Event(), ctx.Event()
    attempted_a, attempted_b = ctx.Event(), ctx.Event()
    a = ctx.Process(target=_process_append, args=(str(target), "A", attempted_a, entered, release))
    b = ctx.Process(target=_process_append, args=(str(target), "B", attempted_b))
    a.start()
    try:
        assert entered.wait(10)
        b.start()
        assert attempted_b.wait(10)
        assert storage.read_financial_json(target)["updates"] == []
    finally:
        release.set()
        a.join(10)
        if b.pid is not None: b.join(10)
    assert a.exitcode == b.exitcode == 0
    assert storage.read_financial_json(target)["updates"] == ["A", "B"]
    assert list(tmp_path.glob("*.tmp")) == []


def test_temp_names_unique_same_parent_and_reader_sees_only_complete_files(tmp_path, monkeypatch):
    target = tmp_path / "portfolio.json"
    storage.write_financial_json(target, empty_portfolio(marker="old"))
    barrier = threading.Barrier(3)
    finish = threading.Event()
    temp_names = []
    real_dump, real_mkstemp = secure_files.json.dump, secure_files.tempfile.mkstemp
    def mkstemp(**kwargs):
        assert Path(kwargs["dir"]) == target.parent
        result = real_mkstemp(**kwargs)
        temp_names.append(Path(result[1]))
        return result
    def dump(value, stream, **kwargs):
        real_dump(value, stream, **kwargs)
        stream.flush()
        barrier.wait(timeout=5)
        assert finish.wait(5)
    monkeypatch.setattr(secure_files.tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(secure_files.json, "dump", dump)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(secure_files.atomic_write_private_json, target, empty_portfolio(marker=x)) for x in ("A", "B")]
        try:
            barrier.wait(timeout=5)
            assert len(set(temp_names)) == 2
            assert all(p.parent == target.parent for p in temp_names)
            for _ in range(20): assert storage.read_financial_json(target)["marker"] == "old"
        finally: finish.set()
        for future in futures: future.result(timeout=5)
    assert storage.read_financial_json(target)["marker"] in ("A", "B")
    assert list(tmp_path.glob("*.tmp")) == []
    if os.name == "posix": assert target.stat().st_mode & 0o777 == 0o600


def test_exception_releases_lock_and_sorted_multi_file_nesting(tmp_path):
    paths = [tmp_path / "portfolio.json", tmp_path / "ledger.json"]
    with pytest.raises(ValueError):
        with storage.financial_locks(paths):
            with storage.financial_locks(reversed(paths)):
                raise ValueError("synthetic mutation failure")
    with storage.financial_locks(reversed(paths)):
        storage.write_financial_json(paths[0], empty_portfolio())


def test_price_fetch_reloads_latest_canonical_before_commit(users, monkeypatch):
    main = import_main_without_loading_real_env()
    data = empty_portfolio(holdings=[{"id": "holding", "code": "SYNTH", "quantity": 1, "current_price": 10}])
    portfolio.write_portfolio(data, "alice")
    async def prices(holdings):
        # Simulate another financial writer while the external read suspends.
        savings.save_bank_account({"name": "concurrent bank", "balance": 50}, "alice")
        return {"prices": {"holding": 20}, "fx_rate": 1400}
    monkeypatch.setattr(main, "is_test_mode", lambda: False)
    monkeypatch.setattr(main, "refresh_all_holdings_prices", prices)
    asyncio.run(main.refresh_prices_for_user("alice"))
    saved = portfolio.read_portfolio("alice")
    assert saved["holdings"][0]["current_price"] == 20
    assert saved["bank_accounts"][0]["balance"] == 50


@pytest.mark.parametrize("provider", ["kb", "toss", "nh", "kis", "kiwoom"])
def test_account_fetch_commits_against_latest_canonical(users, monkeypatch, provider):
    from app.services.broker_holdings_sync import BrokerHoldingsResult, ProviderHoldingScope, ALL_MARKETS
    main = import_main_without_loading_real_env()
    specs = {
        "kb": ("KBOpenAPI", "sync_kb_for_user", "kb_primary", []),
        "toss": ("TossOpenAPI", "sync_toss_for_user", "7", [{"accountSeq": 7, "accountNo": "0000000007"}]),
        "nh": ("NhPlugOpenAPI", "sync_namoo_for_user", "00000000001", [{"acct_no": "00000000001", "acct_type": "01"}]),
        "kis": ("KISOpenAPI", "sync_kis_for_user", "1234567801", [{"account_number": "1234567801", "account_name": "KIS"}]),
        "kiwoom": ("KiwoomOpenAPI", "sync_kiwoom_for_user", "1234567890", [{"account_number": "1234567890", "account_name": "Kiwoom"}]),
    }
    cls, function, key, accounts = specs[provider]
    client = MagicMock(configured=True, last_accounts=accounts, account_cash={key: {"KRW": 0}})
    client._parse_account_no.return_value = ("12345678", "01")
    client._account_name.return_value = "Synthetic NH"
    records = BrokerHoldingsResult.authoritative_result([], [ProviderHoldingScope(key, ALL_MARKETS)], cash_valid=True)
    portfolio.write_portfolio(empty_portfolio(), "alice")
    def concurrent_update():
        savings.save_bank_account({"account_name": "concurrent bank", "balance": 50}, "alice")
    async def holdings():
        if provider not in ("kb", "toss"): concurrent_update()
        return records
    async def quotes(holdings):
        concurrent_update()
        return {}, []
    async def cash(seq):
        concurrent_update()
        return {"KRW": 0}
    client.sync_holdings = AsyncMock(side_effect=holdings)
    client.refresh_prices = AsyncMock(side_effect=quotes)
    client.get_buying_power = AsyncMock(side_effect=cash)
    monkeypatch.setattr(main, cls, lambda **kwargs: client)
    result = asyncio.run(getattr(main, function)("alice"))
    assert result["status"] == "CONFIRMED_EMPTY"
    saved = portfolio.read_portfolio("alice")
    assert saved["bank_accounts"][0]["balance"] == 50
    assert len(saved["accounts"]) == 1
    assert saved["holdings"] == []


def test_async_critical_sections_contain_no_await():
    import ast
    root = ast.parse((Path(__file__).resolve().parents[1] / "app/main.py").read_text(encoding="utf-8"))
    boundaries = []
    for node in ast.walk(root):
        if isinstance(node, ast.With) and any(any(name in ast.unparse(item.context_expr) for name in ("financial_locks", "financial_user_locks")) for item in node.items):
            boundaries.append(node)
            assert not any(isinstance(child, ast.Await) for child in ast.walk(node))
    assert len(boundaries) >= 25
