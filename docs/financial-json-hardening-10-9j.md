# Financial JSON persistence hardening — 10-9j

Base: `7724f146db24d6261a633fa0bbf27bd59555ff4d`.
Branch: `hardening10-9j-financial-json-atomicity`.
Commit title: `hardening: make financial json writes atomic`.

## ROOT_CAUSE / OLD_WRITE_CONTRACT

Atomic rename alone did not protect a service's earlier read. Portfolio,
planning, family and IPO writes shared only a process-local global portfolio
lock; many portfolio callers released it between read and write. Stock history
used a separate non-reentrant global lock. Ledger and income/P&L CRUD had no
shared RMW lock. Fixed `.tmp` / `.json.tmp` names could collide across processes.
Several bootstraps and income writers truncated the canonical target directly.
Most financial replace writers did not flush/fsync. Portfolio/stock readers
treated malformed JSON as empty; the ledger reader also overwrote corruption.

Inventory was completed from source before implementation. Searches covered
`json.dump(s)`, text/byte writes, write/append opens, replace/temporary files,
private atomic helper use, writer callers and cross-file rollback paths. No
production financial file was opened to build this inventory.

## PERSISTENCE_INVENTORY

Paths below are existing path families, not accessed financial files. `U` means
the canonical per-user directory returned by `get_user_data_dir`.
Atomic/lock columns describe the **base**, before this branch.

| Path family | Reader | Writer / callers | Classification | RMW | Atomic replace at base | Lock at base | Hardened / exclusion reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `U/portfolio.json` | `portfolio.read_portfolio`; raw planning/family/IPO reads | `write_portfolio`; account sync/manual CRUD/import; savings/real estate; planning; family; IPO applications/allocation | Authoritative financial state, including net-worth history in `settings.wealth_planning.history` | Yes | Updates yes, fixed temp; bootstrap no; no fsync | Global module RLock; many caller RMW gaps; no advisory lock | Yes: every production writer of this target uses its canonical path domain |
| `U/asset_records.json` | `read_asset_records`, dashboard history lookup | `write_asset_records`, upsert/delete, manual/daily-close stock snapshots | Authoritative stock/asset history | Yes | Update fixed temp; bootstrap direct; no fsync | Separate global Lock around final read/write only | Yes: full upsert/delete RMW and atomic bootstrap/write |
| `U/ledger.json` | `read_ledger`, strict import reader, overdraft reference check | transaction/card/recurring CRUD; file import; coordinated portfolio commit/rollback | Authoritative ledger | Yes | Fixed temp, no fsync; corrupt-read bootstrap could overwrite | No common RMW lock | Yes: ledger RMW; sorted ledger+portfolio lock when balances also change |
| `U/dividend_records.json` | normal and strict import readers | create/update/delete/clear/file import/FX recalculation; Toss WTS income import | Authoritative received dividend/interest history | Yes | Direct canonical write | WTS import-only module RLock; other writers not in domain | Yes: full record/dedup RMW and atomic writer |
| `U/realized_pnl_records.json` | normal/readonly strict reader; IPO sale candidates | CRUD/clear/broker-clear/file import/FX recalculation; all broker import paths | Authoritative realized-P&L history | Yes | Direct canonical write | Broker-specific import locks and portfolio-only IPO guard; no shared record lock | Yes: record RMW; IPO link/delete guards lock portfolio+P&L together |
| `U/dividend_forecast_snapshots.json` | snapshot listing/storage reader | frozen forecast upsert/manual/daily-close capture | Authoritative historical observation: current forecasts cannot reconstruct past captured basis | Yes | Fixed temp; no fsync | Global process RLock | Yes: path lock and private atomic writer; strict snapshot validation retained |
| General backup/export/import | existing family readers | `backup_restore.restore_general_data`; user initialization; startup legacy financial copy; explicit WTS code migration entry points | Writer entry points to the authoritative families above | Yes/check-create/replacement | Mixed; restore rollback used snapshot rename; copy/bootstrap non-atomic | Restore-only settings advisory lock; migrations not in writer domains | Yes: shared sorted financial domains, including backup snapshot/rollback; migration code changed but **no migration executed on user data** |
| `U/period_rates.json`; legacy period cache | portfolio dashboard | portfolio period-rate cache writer | Derived/cache | Yes | Direct cache write | No | No: external market period observations are rebuildable; no financial writer ownership |
| `historical_fx_cache.json` | historical FX lookup | historical FX cache saver | Market-data cache | Yes | Direct write | No | No: rebuildable FX observations; financial record calculations unchanged |
| `stock_master_cache.json` | stock/security lookup | stock master cache builder | Reference cache | Yes | Direct write | No | No: rebuildable security master; legacy financial files are read-only lookup inputs here |
| Provider price/token caches | Toss price reader; KB/NH/KIS/Kiwoom token readers | provider cache helpers | Market cache / credentials | Mixed | Price direct; token private atomic helper | Provider-local/mixed | No: not canonical holdings; no token/config/provider behavior rewrite |
| `ipo/market.json`; score/reference paths | IPO store/presentation/scoring | market upsert/refresh/backfill; score-snapshot path is declared without an active writer | IPO market/reference dataset, including research annotations | Yes | Fixed temp replace | IPO store RLock | No: not user holdings, applied-state or financial history; those are in portfolio and **are** protected |
| `ipo/notification_state.json`; IPO action files | notifier/actions | notifier dedup / action save | Execution metadata | Yes | Replace; actions fsync | Notifier/action process + advisory locks | No: workflow execution state, not financial state |
| `automation/execution_state.json` and `automation/account_pre_sync/*.json` | dispatcher/status/pre-sync close reader | execution-state / pre-sync service | Execution metadata | Yes | Atomic replace + fsync | Existing execution/advisory locks and run-id/CAS | No: already separate execution contract; unchanged |
| Notification history / dividend intelligence alert state | notification/alert services | provider dispatch/dedup history | Execution metadata | Yes | History unique-temp/fsync; alert fixed-temp replace | History path/advisory; alert module lock | No: send/dedup metadata, not received income records |
| `U/settings.json`; system settings | settings services | settings patch/system patch | Settings | Yes | Fixed temp + fsync + replace | Settings path/advisory locks | No: stored settings/schema unaffected |
| OpenAPI/KRX/DART/provider secrets; Kakao tokens; system signing secret | config/secret readers | secret/config helpers | Settings / credentials | Yes/replacement | Private atomic helper or equivalent fsync+replace | Mixed settings/provider locks | No: credential logic/data excluded; shared helper retains private permissions |
| `U/*_account_mapping.json` | broker destination resolution | broker import mapping helpers in main | Integration settings (destination UUID binding) | Yes | Unique temp replace | Existing broker import locks | No: financial record classification+commit locks added, mapping settings/schema unchanged |
| KFTC token/OAuth/accounts JSON | KFTC storage | KFTC private atomic helper | Credentials / discovered-account integration settings | Mixed | Private atomic helper | Operation-specific | No: discovered mappings do not own canonical balances; savings/portfolio balance writers are protected |
| KFTC bank transaction sequence | KFTC sequence allocator | `next_bank_tran_sequence` | Execution metadata | Yes | Private atomic helper | Thread + msvcrt/flock advisory | No: already owns its independent monotonic sequence contract |
| WTS runtime/login/auth-operation JSON | WTS runtime helpers | login/auth metadata helpers | Execution metadata | Yes/replacement | Replace | Existing operation/runtime locks | No: no realized-P&L feed/runtime behavior change |
| `users.json`, user ID migration | user manager/identity service | registry save/explicit identity migration | Authentication/settings | Yes | Fixed temp replace / unique migration temp+fsync | Identity validation, not financial lock | No: authentication/username/ID semantics excluded; only financial bootstrap code in user_manager changed |
| HTTP JSON/export/preview reports | endpoint/client | `json.dumps` responses; tools preview output | Response / derived report artifact | No financial RMW | N/A | N/A | No: does not persist authoritative financial state |

## NEW_ATOMIC_WRITE_CONTRACT / TEMP_FILE_CONTRACT / FSYNC_CONTRACT

`financial_json.write_financial_json` validates existing state and candidate
containers under the path lock, then reuses `secure_files`:

1. Parent directory exists; private unique `mkstemp` is created in that directory.
2. Serialize complete JSON with the existing keys and `ensure_ascii=False`;
   reject non-finite/non-serializable values.
3. Flush, fsync the open temp descriptor, close, then `os.replace`.
4. Best-effort cleanup on failure; the canonical file is never pre-unlinked.

Existing Windows bounded PermissionError retry and POSIX private mode 0600
remain. Backup rollback reuses the same low-level atomic helper to restore
**exact previous bytes**, rather than reformatting the backup. Temporary backup
copies are staging data, never canonical targets. Successful/injected-failure
tests observe zero orphan `.tmp` files. Sidecar `.lock` files intentionally remain
and contain no financial JSON; deleting them would split the advisory domain.

## LOCK_IDENTITY / FULL_RMW_LOCK_BOUNDARY / DEADLOCK_ANALYSIS

Identity is `normcase(Path(path).resolve())`: relative/absolute/symlink aliases
and Windows case aliases share a registry entry and sidecar. Each canonical
file has a reentrant thread lock and an OS advisory lock (Windows `msvcrt`,
POSIX `flock`), using the same native primitive pattern inspected in existing
settings/execution/KFTC locking. Those existing context managers could not be
reused directly: they are non-reentrant and/or globally serialize unrelated
files. This narrow financial helper leaves their contracts untouched.
User transaction targets resolve through the owning service's actual canonical
path getter, so storage-directory overrides and writer paths cannot diverge.

Synchronous service decorators and explicit raw portfolio mutation contexts
cover read → validate → modify → atomic write. Main's asynchronous handlers
finish request/provider reads before entering synchronous RMW sections. KB/Toss
retain pre-fetch ambiguity validation and revalidate against the latest locked
portfolio after optional quote/cash reads. Other broker holdings reads already
precede canonical mutation. Price/FX refresh re-reads latest state after await.
No financial critical section in main contains an `await` (static regression).

Coordinated targets acquire unique canonical paths in lexical order. Ledger
balance changes/rollback lock ledger+portfolio; P&L link/delete lock
portfolio+P&L; restore holds all affected domains from backup copy through
rollback. Recursive calls reuse the already-held advisory handle through
thread-local depth and an RLock. No global financial lock remains. Registry
guard only selects a lock; it never surrounds financial I/O. Existing broker
mapping locks precede financial import locks; financial services do not acquire
those broker locks in reverse. Busy acquisition is bounded and fail-closed.
Exception paths release locks.

## CORRUPTION_CONTRACT / MISSING_BOOTSTRAP_CONTRACT / READER_CONSISTENCY

Missing file alone permits existing bootstrap/default behavior. Malformed JSON,
invalid root/container types and non-finite JSON constants produce sanitized
`FinancialStorageError`, or the existing ledger/dividend/P&L domain storage
error where that contract already exists. Both ordinary reads and writer
preflight refuse corrupt authoritative state. No empty rewrite/repair occurs.

Existing new-user templates keep their JSON shape. The old empty P&L list
emitted by initialization remains readable; legacy stock-history lists also
remain readable. No stored files are migrated/normalized by this task. ID,
owner, date, calculation, API and filesystem path meanings remain unchanged.

General readonly access can see old or new complete files without a global
lock. Bootstrap checks use the path lock. RMW readers always remain inside their
transaction; raw readonly IPO/dashboard history reads use the strict complete
snapshot reader. Existing derived snapshot calculations are unchanged.
Existing-file ordinary reads do not create sidecars or write canonical bytes;
`test_readonly_existing_documents_do_not_create_lock_files` verifies this.

## EVIDENCE / REGRESSIONS

`tests/test_financial_json_atomicity.py` provides deterministic Event/Barrier
tests, not sleeps to arrange writer races:

| Requirement | Test / evidence |
| --- | --- |
| Serialization/temp-write/flush/fsync/replace failure | `test_failure_preserves_previous_bytes_and_cleans_unique_temp` (5 cases); previous bytes preserved=yes; truncated canonical observed=0; orphan temp=0 |
| Temp creation failure | `test_temp_creation_failure_preserves_previous_bytes`; old bytes preserved; orphan temp=0 |
| Corruption vs missing | 5 financial families × 3 corrupt fixtures; corrupt→empty bootstrap=0; corrupt overwrite=0; 5 missing/bootstrap cases remain supported |
| Same file RMW | `test_same_portfolio_rmw_preserve_two_updates`; writer count=2; preserved updates=2; lost updates=0 |
| Cross-module shared portfolio | `test_different_modules_same_canonical_path_preserve_both_updates`; savings + portfolio migration service, both synthetic changes preserved |
| Record append RMW | `test_record_rmw_preserves_two_appends` (stock/ledger/dividend/P&L); 2 writers → 2 records for every family |
| Cross-process | `test_cross_process_rmw_preserves_two_updates`; 2 spawned processes → `[A,B]`; lost updates=0 |
| Independent user/file | `test_different_user_and_file_do_not_wait_for_held_portfolio`; Bob portfolio and Alice stock record complete while Alice portfolio remains held |
| Aliases / reentrancy / exception release | `test_path_aliases_and_recursive_writes_share_one_domain`; `test_exception_releases_lock_and_sorted_multi_file_nesting` |
| Temp/readonly consistency | `test_temp_names_unique_same_parent_and_reader_sees_only_complete_files`; 2 simultaneous helper temps unique, same target parent; 20 old complete samples + new complete result; partial JSON=0; orphan temp=0 |
| Async canonical handoff | `test_account_fetch_commits_against_latest_canonical` (all 5 brokers); concurrent bank update survives; `test_price_fetch_reloads_latest_canonical_before_commit` |
| Async lock boundary | `test_async_critical_sections_contain_no_await` |
| ACCOUNT_PRESYNC_REGRESSION / DAILY_CLOSE_REGRESSION | Existing `AccountPreSyncTests.test_success_persists_and_close_has_zero_account_calls_and_one_snapshot`: 20:50 5 canonical syncs; stock/net snapshots=0; 21:00 KB/Toss/NH/KIS/Kiwoom holdings/cash/API entry calls=0; stock/net snapshot entry calls=1 each. Existing persistence-failure, confirmed-empty, stale/missing and manual-sync tests retained |
| Backup race / failure | Related test now verifies normal financial writer waits until rollback releases shared domains, then its update survives; no assertion weakening for unrelated behavior |
| User isolation / sidecars | Existing user marker separation retained; exact 10 JSON files + exact 10 corresponding advisory sidecars, no extra files |
| Descriptor ownership | `test_stream_owned_descriptor_is_not_closed_twice_on_failure`; `test_fdopen_failure_closes_still_unowned_descriptor`; cleanup cannot close a descriptor already handed to and closed by a stream |

### Validation results

| Check | Result |
| --- | --- |
| Expanded focused portfolio/records/ledger/restore/provider/import/IPO regression suite | 470 passed, 199 subtests passed |
| Additional FX/notification regression suite | 40 passed, 16 subtests passed |
| Final-source atomicity/isolation/pre-sync/daily-close suite | 105 passed, 92 subtests passed |
| Final full `PYTHONPATH=tests` pytest | **1 failed, 3087 passed, 3 skipped, 768 subtests passed**, 528.60 seconds; see separate Chrome result below |
| Changed Python source hash equality between repository and test copy | 32/32 identical |
| Changed Python `py_compile` | 32 passed |
| `git diff --check` | Passed |

The full-run failure was the unchanged native Chrome test
`test_income_bucket_drilldown.py::test_income_bucket_runtime[day_selection_non_painted_geometry]`,
with `DAY keyboard target unpainted and pointer-inert`. The exact-base isolated
A/B run passed (1 passed, 3.33 seconds); the branch isolated run passed
(1 passed, 2.27 seconds). All 44 frontend static files and the three relevant
test/preview files were byte-identical between base and branch. The earlier
full branch run also passed this Chrome test. The intermittent full-run failure
is reported separately; the final full suite is **not** described as green,
and no UI code or Chrome assertion was changed. A/B did not reproduce the
failure on base, so it does not establish a deterministic baseline failure.

Tests ran against explicit temporary source copies with synthetic data and
guarded network, `PYTHONPATH=tests`; the environment variable was restored in
`finally`. Real `data/`, `.env`, credentials and production provider calls were
not accessed. No schema/path migration, UI/calculation, scheduler, settings or
credential behavior changes. No push/PR/merge.

## CHANGED_FILES

Changed files: 33 (32 Python files and this report). Deleted files: none.
The complete changed-file list is:

```text
app/main.py
app/services/asset_records.py
app/services/backup_restore.py
app/services/dividend_forecast_snapshots.py
app/services/dividend_records.py
app/services/family_members.py
app/services/financial_json.py
app/services/ipo/allocation.py
app/services/ipo/applications.py
app/services/ipo/link_integrity.py
app/services/ipo/presentation.py
app/services/ledger.py
app/services/planning.py
app/services/pnl_broker_clear.py
app/services/pnl_records.py
app/services/portfolio.py
app/services/real_estate.py
app/services/savings.py
app/services/secure_files.py
app/services/toss_wts_income_code_migration.py
app/services/toss_wts_realized_code_migration.py
app/services/user_manager.py
docs/financial-json-hardening-10-9j.md
tests/test_account_display_order.py
tests/test_account_import.py
tests/test_backup_restore_safety.py
tests/test_broker_holdings_authoritative_empty.py
tests/test_broker_sync_safety.py
tests/test_data_isolation_regression.py
tests/test_financial_json_atomicity.py
tests/test_notification_action_reliability.py
tests/test_planning_regression.py
tests/test_toss_wts_fx_recalc_guard.py
```
