"""Broker-scoped realized P/L destination, mapping, and source validation."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

from app.services.kb_openapi import KBOpenAPI
from app.services.kiwoom_openapi import KiwoomOpenAPI
from app.services.nhplug_openapi import NhPlugOpenAPI


def create_broker_realized_destination(runtime: ModuleType) -> dict[str, object]:
    # Resolve app bindings at call time so existing helper patches also reach nested calls.
    def _realized_destination_resolution(
        username: str,
        provider: str,
        *,
        provider_account_identity: object = None,
        mapped_destination_account_id: object = None,
    ):
        """Resolve a provider source only to same-broker Wealth accounts."""
        accounts = runtime.read_portfolio(username=username).get("accounts", [])
        return runtime.resolve_realized_destination_candidates(
            provider,
            accounts,
            provider_account_identity=provider_account_identity,
            mapped_destination_account_id=mapped_destination_account_id,
        )

    def _realized_destination_payload(resolution: Any) -> dict[str, Any]:
        return {
            "candidate_account_ids": list(resolution.candidate_account_ids),
            "auto_selected_account_id": resolution.auto_selected_account_id,
            "destination_resolution": resolution.reason,
            "mapping_status": resolution.mapping_status,
        }

    def _require_realized_destination(
        username: str,
        provider: str,
        account_id: object,
        *,
        provider_account_identity: object = None,
        mapped_destination_account_id: object = None,
    ) -> dict[str, Any]:
        if not isinstance(account_id, str) or not account_id.strip():
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "DESTINATION_INVALID", "message": "Explicit destination account is required"},
            )
        accounts = runtime.read_portfolio(username=username).get("accounts", [])
        try:
            account, _ = runtime.validate_realized_destination(
                provider,
                accounts,
                account_id,
                provider_account_identity=provider_account_identity,
                mapped_destination_account_id=mapped_destination_account_id,
            )
            return account
        except ValueError as exc:
            code = str(exc)
            if code in {"CROSS_BROKER_MAPPING", "DESTINATION_MAPPING_CONFLICT", "DESTINATION_IDENTITY_CONFLICT"}:
                status = 409
                message = "Source account destination mapping conflicts with this import"
            else:
                status = 400
                message = "Destination account must belong to the same broker"
            raise runtime.HTTPException(status_code=status, detail={"code": code, "message": message}) from exc

    # KIS mappings
    def _kis_mapping_file(username: str) -> Path:
        from app.services.user_manager import get_user_data_dir
        return get_user_data_dir(username) / "kis_account_mapping.json"

    def _read_kis_mapping(username: str) -> dict[str, str]:
        path = runtime._kis_mapping_file(username)
        if not path.exists():
            return {}
        try:
            value = runtime.json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _assert_kis_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
        existing = runtime._read_kis_mapping(username).get(source_key)
        if existing and existing != destination_id:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "KIS destination mapping conflicts with this import"},
            )
        return existing == destination_id

    def _write_kis_mapping(username: str, source_key: str, destination_id: str) -> bool:
        if runtime._assert_kis_mapping_compatible(username, source_key, destination_id):
            return False
        path = runtime._kis_mapping_file(username)
        mapping = runtime._read_kis_mapping(username)
        mapping[source_key] = destination_id
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{runtime.uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(runtime.json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            runtime.os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        return True

    # NH source accounts and mappings
    async def _resolve_nh_source_account(client: NhPlugOpenAPI, source_key: str) -> tuple[str, str]:
        """Resolve an opaque client key to a server-side NH account number."""
        for account in await client._accounts():
            act_no = str(account.get("acct_no") or account.get("act_no") or "").strip()
            if act_no and runtime.compute_nh_account_key(act_no) == source_key:
                return act_no, runtime.mask_nh_account(act_no)
        raise runtime.HTTPException(status_code=400, detail={"code": "SCOPE_MISMATCH", "message": "NH source account is unavailable"})

    def _nh_mapping_file(username: str) -> Path:
        from app.services.user_manager import get_user_data_dir
        return get_user_data_dir(username) / "nh_account_mapping.json"

    def _read_nh_mapping(username: str) -> dict[str, str]:
        path = runtime._nh_mapping_file(username)
        if not path.exists(): return {}
        try:
            value = runtime.json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _assert_nh_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
        """Return whether the exact mapping exists; reject a conflicting mapping."""
        existing = runtime._read_nh_mapping(username).get(source_key)
        if existing and existing != destination_id:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "NH destination mapping conflicts with this import"},
            )
        return existing == destination_id

    def _write_nh_mapping(username: str, source_key: str, destination_id: str) -> bool:
        """Persist one non-conflicting mapping atomically; return whether it changed."""
        if runtime._assert_nh_mapping_compatible(username, source_key, destination_id):
            return False
        path = runtime._nh_mapping_file(username)
        mapping = runtime._read_nh_mapping(username)
        mapping[source_key] = destination_id
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{runtime.uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(runtime.json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            runtime.os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        return True

    def _nh_imported_items_match_destination(
        result: dict[str, Any], current: list[dict[str, Any]], source_key: str, destination_id: str,
    ) -> bool:
        """Prove every selected item is an existing NH row for this source/destination."""
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list) or not items or any(item.get("status") != "ALREADY_IMPORTED" for item in items):
            return False
        records_by_fingerprint = {
            str(record.get("source_fingerprint")): record
            for record in current
            if record.get("source") == "nh" and record.get("source_fingerprint")
        }
        for item in items:
            record = records_by_fingerprint.get(str(item.get("fingerprint") or ""))
            if (
                not record
                or record.get("source") != "nh"
                or str(record.get("source_account_key") or "") != source_key
                or str(record.get("destination_account_id") or "") != destination_id
            ):
                return False
        return True

    def _assert_nh_source_records_destination(
        current: list[dict[str, Any]], source_key: str, destination_id: str,
    ) -> None:
        """Prevent one opaque NH source from silently spanning destinations."""
        conflict = any(
            record.get("source") == "nh"
            and str(record.get("source_account_key") or "") == source_key
            and str(record.get("destination_account_id") or "") != destination_id
            for record in current
        )
        if conflict:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "NH source records belong to a different destination"},
            )

    def _read_nh_pnl_records_strict(username: str) -> list[dict[str, Any]]:
        try:
            return runtime.read_pnl_records_readonly(username=username)
        except runtime.PnlRecordsStorageError as exc:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "PNL_STORAGE_INVALID", "message": "Realized P/L storage requires review"},
            ) from exc

    def _nh_destination(username: str, account_id: object, source_key: str, act_no: str) -> dict[str, Any]:
        return runtime._require_realized_destination(
            username, "nh", account_id,
            provider_account_identity=act_no,
            mapped_destination_account_id=runtime._read_nh_mapping(username).get(source_key),
        )

    # KB source accounts and mappings
    def _kb_mapping_file(username: str) -> Path:
        from app.services.user_manager import get_user_data_dir
        return get_user_data_dir(username) / "kb_account_mapping.json"

    def _read_kb_mapping(username: str) -> dict[str, str]:
        path = runtime._kb_mapping_file(username)
        if not path.exists():
            return {}
        try:
            value = runtime.json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, runtime.json.JSONDecodeError) as exc:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_INVALID", "message": "KB destination mapping requires review"},
            ) from exc
        if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_INVALID", "message": "KB destination mapping requires review"},
            )
        return value

    def _assert_kb_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
        existing = runtime._read_kb_mapping(username).get(source_key)
        if existing and existing != destination_id:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "KB destination mapping conflicts with this import"},
            )
        return existing == destination_id

    def _write_kb_mapping(username: str, source_key: str, destination_id: str) -> bool:
        if runtime._assert_kb_mapping_compatible(username, source_key, destination_id):
            return False
        path = runtime._kb_mapping_file(username)
        mapping = runtime._read_kb_mapping(username)
        mapping[source_key] = destination_id
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{runtime.uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(runtime.json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            runtime.os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        return True

    def _kb_destination(username: str, account_id: object, source_key: str) -> dict[str, Any]:
        return runtime._require_realized_destination(
            username, "kb", account_id,
            mapped_destination_account_id=runtime._read_kb_mapping(username).get(source_key),
        )

    def _read_kb_pnl_records_strict(username: str) -> list[dict[str, Any]]:
        try:
            return runtime.read_pnl_records_readonly(username=username)
        except runtime.PnlRecordsStorageError as exc:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "PNL_STORAGE_INVALID", "message": "Realized P/L storage requires review"},
            ) from exc

    def _assert_kb_source_records_destination(
        current: list[dict[str, Any]], source_key: str, destination_id: str,
    ) -> None:
        if any(
            record.get("source") == "kb"
            and str(record.get("source_account_key") or "") == source_key
            and str(record.get("destination_account_id") or "") != destination_id
            for record in current
        ):
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "KB source records belong to a different destination"},
            )

    def _kb_imported_items_match_destination(
        result: dict[str, Any], current: list[dict[str, Any]], source_key: str, destination_id: str,
    ) -> bool:
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list) or not items or any(item.get("status") != "ALREADY_IMPORTED" for item in items):
            return False
        records_by_fingerprint = {
            str(record.get("source_fingerprint")): record
            for record in current
            if record.get("source") == "kb" and record.get("source_fingerprint")
        }
        for item in items:
            record = records_by_fingerprint.get(str(item.get("fingerprint") or ""))
            if (
                not record
                or str(record.get("source_account_key") or "") != source_key
                or str(record.get("destination_account_id") or "") != destination_id
            ):
                return False
        return True

    def _verify_kb_source_context(client: KBOpenAPI, source_key: str) -> tuple[str, str]:
        try:
            current_key, label = client.get_realized_source_account_state()
        except runtime.KBOpenAPIError as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "KB_NOT_READY", "message": "KB realized account configuration is unavailable"},
            ) from exc
        if not source_key or current_key != source_key:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "SCOPE_MISMATCH", "message": "KB source account changed"},
            )
        return current_key, label

    # Kiwoom source accounts and mappings
    def _kiwoom_mapping_file(username: str) -> Path:
        from app.services.user_manager import get_user_data_dir
        return get_user_data_dir(username) / "kiwoom_account_mapping.json"

    def _read_kiwoom_mapping(username: str) -> dict[str, str]:
        path = runtime._kiwoom_mapping_file(username)
        if not path.exists():
            return {}
        try:
            value = runtime.json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, runtime.json.JSONDecodeError) as exc:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_INVALID", "message": "Kiwoom destination mapping requires review"},
            ) from exc
        if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_INVALID", "message": "Kiwoom destination mapping requires review"},
            )
        return value

    def _assert_kiwoom_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
        existing = runtime._read_kiwoom_mapping(username).get(source_key)
        if existing and existing != destination_id:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "Kiwoom destination mapping conflicts with this import"},
            )
        return existing == destination_id

    def _write_kiwoom_mapping(username: str, source_key: str, destination_id: str) -> bool:
        if runtime._assert_kiwoom_mapping_compatible(username, source_key, destination_id):
            return False
        path = runtime._kiwoom_mapping_file(username)
        mapping = runtime._read_kiwoom_mapping(username)
        mapping[source_key] = destination_id
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{runtime.uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(runtime.json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            runtime.os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        return True

    def _kiwoom_destination(username: str, account_id: object, source_key: str, acct_no: str) -> dict[str, Any]:
        return runtime._require_realized_destination(
            username, "kiwoom", account_id,
            provider_account_identity=acct_no,
            mapped_destination_account_id=runtime._read_kiwoom_mapping(username).get(source_key),
        )

    def _read_kiwoom_pnl_records_strict(username: str) -> list[dict[str, Any]]:
        try:
            return runtime.read_pnl_records_readonly(username=username)
        except runtime.PnlRecordsStorageError as exc:
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "PNL_STORAGE_INVALID", "message": "Realized P/L storage requires review"},
            ) from exc

    def _assert_kiwoom_source_records_destination(
        current: list[dict[str, Any]], source_key: str, destination_id: str,
    ) -> None:
        if any(
            record.get("source") == "kiwoom"
            and str(record.get("source_account_key") or "") == source_key
            and str(record.get("destination_account_id") or "") != destination_id
            for record in current
        ):
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "Kiwoom source records belong to a different destination"},
            )

    def _kiwoom_imported_items_match_destination(
        result: dict[str, Any], current: list[dict[str, Any]], source_key: str, destination_id: str,
    ) -> bool:
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list) or not items or any(item.get("status") != "ALREADY_IMPORTED" for item in items):
            return False
        records_by_fingerprint = {
            str(record.get("source_fingerprint")): record
            for record in current
            if record.get("source") == "kiwoom" and record.get("source_fingerprint")
        }
        for item in items:
            record = records_by_fingerprint.get(str(item.get("fingerprint") or ""))
            if (
                not record
                or str(record.get("source_account_key") or "") != source_key
                or str(record.get("destination_account_id") or "") != destination_id
            ):
                return False
        return True

    async def _verify_kiwoom_source_context(
        client: KiwoomOpenAPI, source_key: str,
    ) -> tuple[str, str, str]:
        try:
            account_no, current_key, label = await client.get_realized_source_account_context()
        except runtime.KiwoomOpenAPIError as exc:
            raise runtime.HTTPException(
                status_code=502,
                detail={"code": "KIWOOM_API_ERROR", "message": "Kiwoom source account unavailable"},
            ) from exc
        if not source_key or current_key != source_key:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "SCOPE_MISMATCH", "message": "Kiwoom source account changed"},
            )
        return account_no, current_key, label

    return {
        "_realized_destination_resolution": _realized_destination_resolution,
        "_realized_destination_payload": _realized_destination_payload,
        "_require_realized_destination": _require_realized_destination,
        "_kis_mapping_file": _kis_mapping_file,
        "_read_kis_mapping": _read_kis_mapping,
        "_assert_kis_mapping_compatible": _assert_kis_mapping_compatible,
        "_write_kis_mapping": _write_kis_mapping,
        "_resolve_nh_source_account": _resolve_nh_source_account,
        "_nh_mapping_file": _nh_mapping_file,
        "_read_nh_mapping": _read_nh_mapping,
        "_assert_nh_mapping_compatible": _assert_nh_mapping_compatible,
        "_write_nh_mapping": _write_nh_mapping,
        "_nh_imported_items_match_destination": _nh_imported_items_match_destination,
        "_assert_nh_source_records_destination": _assert_nh_source_records_destination,
        "_read_nh_pnl_records_strict": _read_nh_pnl_records_strict,
        "_nh_destination": _nh_destination,
        "_kb_mapping_file": _kb_mapping_file,
        "_read_kb_mapping": _read_kb_mapping,
        "_assert_kb_mapping_compatible": _assert_kb_mapping_compatible,
        "_write_kb_mapping": _write_kb_mapping,
        "_kb_destination": _kb_destination,
        "_read_kb_pnl_records_strict": _read_kb_pnl_records_strict,
        "_assert_kb_source_records_destination": _assert_kb_source_records_destination,
        "_kb_imported_items_match_destination": _kb_imported_items_match_destination,
        "_verify_kb_source_context": _verify_kb_source_context,
        "_kiwoom_mapping_file": _kiwoom_mapping_file,
        "_read_kiwoom_mapping": _read_kiwoom_mapping,
        "_assert_kiwoom_mapping_compatible": _assert_kiwoom_mapping_compatible,
        "_write_kiwoom_mapping": _write_kiwoom_mapping,
        "_kiwoom_destination": _kiwoom_destination,
        "_read_kiwoom_pnl_records_strict": _read_kiwoom_pnl_records_strict,
        "_assert_kiwoom_source_records_destination": _assert_kiwoom_source_records_destination,
        "_kiwoom_imported_items_match_destination": _kiwoom_imported_items_match_destination,
        "_verify_kiwoom_source_context": _verify_kiwoom_source_context,
    }
