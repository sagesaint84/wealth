from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request


def _ipo_market_record(ipo_id: str) -> dict[str, Any]:
    from app.services.ipo.store import read_market_store
    market = read_market_store()
    ipo = next((item for item in market.get("ipos", []) if str(item.get("ipo_id") or "") == ipo_id), None)
    if not isinstance(ipo, dict):
        raise HTTPException(status_code=404, detail={"code": "IPO_NOT_FOUND", "message": "IPO schedule not found"})
    return ipo


def _ipo_source_brokers(ipo_id: str) -> list[dict[str, str]]:
    """Return only canonical brokers explicitly named by this market IPO."""
    from app.services.broker_registry import get_display_name, normalize_broker
    ipo = _ipo_market_record(ipo_id)
    managers = ipo.get("lead_managers")
    if not isinstance(managers, list):
        managers = []
    brokers: list[dict[str, str]] = []
    seen: set[str] = set()
    for manager in managers:
        broker_id = normalize_broker(str(manager))
        if broker_id and broker_id not in seen:
            seen.add(broker_id)
            brokers.append({"broker_id": broker_id, "display_name": get_display_name(broker_id) or broker_id})
    return brokers


def _ipo_source_broker_ids(ipo_id: str) -> set[str]:
    return {item["broker_id"] for item in _ipo_source_brokers(ipo_id)}


def _validate_ipo_source_broker(ipo_id: str, broker_value: object) -> str | None:
    from app.services.broker_registry import normalize_broker

    broker_id = normalize_broker(str(broker_value) if broker_value is not None else None)
    if broker_id is None:
        return None
    if broker_id not in _ipo_source_broker_ids(ipo_id):
        raise HTTPException(
            status_code=400,
            detail={"code": "IPO_BROKER_NOT_AVAILABLE", "message": "Broker is not an IPO lead manager"},
        )
    return broker_id


def _ipo_listing_date(ipo: dict[str, Any]) -> str | None:
    value = ipo.get("actual_listing_date") or ipo.get("expected_listing_date")
    value = str(value or "").strip()
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None


def create_ipo_applications_router(
    *,
    get_current_username: Callable[[Request], str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/ipo/applications")
    async def get_ipo_applications(request: Request) -> dict:
        """Return user family IPO applications and revision."""
        username = get_current_username(request)
        from app.services.ipo.applications import get_user_applications
        return get_user_applications(username)

    @router.put("/api/ipo/visibility/{ipo_id}")
    async def put_ipo_visibility(ipo_id: str, request: Request) -> dict:
        username = get_current_username(request)
        body = await request.json()
        if not isinstance(body, dict) or type(body.get("revision")) is not int:
            raise HTTPException(status_code=400, detail="revision is required")
        from app.services.ipo.applications import set_schedule_visibility, ApplicationRevisionConflict, InvalidApplicationError
        try:
            return set_schedule_visibility(username, ipo_id, excluded=body.get("excluded"), client_revision=body["revision"])
        except ApplicationRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidApplicationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/api/ipo/applications/{ipo_id}")
    async def put_ipo_application(ipo_id: str, request: Request) -> dict:
        """Update family application status for a specific IPO with revision locking."""
        username = get_current_username(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid request body")

        applied_owners = body.get("applied_owners")
        revision = body.get("revision")
        if applied_owners is None or revision is None:
            raise HTTPException(status_code=400, detail="'applied_owners' and 'revision' are required.")

        from app.services.ipo.applications import (
            update_user_application,
            ApplicationRevisionConflict,
            InvalidApplicationError,
        )
        try:
            result = update_user_application(
                username=username,
                ipo_id=ipo_id,
                applied_owners=applied_owners,
                client_revision=int(revision),
            )
            return result
        except ApplicationRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidApplicationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/ipo/applications/{ipo_id}/broker-options")
    async def get_ipo_application_broker_options(ipo_id: str, request: Request) -> dict:
        """Return canonical broker options declared by the market schedule only."""
        username = get_current_username(request)
        return {"ipo_id": ipo_id, "brokers": _ipo_source_brokers(ipo_id)}

    @router.get("/api/ipo/applications/{ipo_id}/account-candidates")
    async def get_ipo_application_account_candidates(
        ipo_id: str,
        request: Request,
        owner: str,
        broker: str,
        remap: bool = False,
    ) -> dict:
        """Return backend-authorized, sanitized account candidates for one applicant."""
        username = get_current_username(request)
        broker_id = _validate_ipo_source_broker(ipo_id, broker)
        if broker_id is None:
            return {
                "ipo_id": ipo_id,
                "owner": owner,
                "broker_id": None,
                "candidates": [],
                "auto_selected_account_id": None,
                "resolution_status": "BROKER_UNKNOWN",
                "mapping_status": "not_checked",
            }
        from app.services.ipo.applications import InvalidApplicationError, resolve_user_application_account
        try:
            resolution = resolve_user_application_account(
                username, ipo_id, owner, broker_id, ignore_existing_mapping=remap,
            )
        except InvalidApplicationError as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_APPLICANT", "message": str(exc)}) from exc
        return {
            "ipo_id": ipo_id,
            "owner": owner,
            "broker_id": resolution.broker_id,
            "candidates": list(resolution.candidates),
            "auto_selected_account_id": resolution.auto_selected_account_id,
            "resolution_status": resolution.resolution_status,
            "mapping_status": resolution.mapping_status,
        }

    @router.put("/api/ipo/applications/{ipo_id}/applicants/{owner}/account")
    async def put_ipo_application_account(ipo_id: str, owner: str, request: Request) -> dict:
        """Persist an applicant's canonical Wealth UUID after broker validation."""
        username = get_current_username(request)
        body = await request.json()
        if not isinstance(body, dict) or "broker" not in body or "account_id" not in body or "revision" not in body:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "broker, account_id, and revision are required"})
        broker_id = _validate_ipo_source_broker(ipo_id, body.get("broker"))
        if broker_id is None:
            raise HTTPException(status_code=400, detail={"code": "BROKER_UNKNOWN", "message": "Broker is unknown"})
        from app.services.ipo.applications import (
            ApplicationAccountMappingConflict,
            ApplicationRevisionConflict,
            InvalidApplicationError,
            set_user_application_account,
        )
        try:
            return set_user_application_account(
                username, ipo_id, owner, broker_id, body.get("account_id"), int(body["revision"]),
            )
        except ApplicationRevisionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "REVISION_CONFLICT", "message": str(exc)}) from exc
        except ApplicationAccountMappingConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "MAPPING_CONFLICT", "message": "Applicant account mapping conflicts"}) from exc
        except InvalidApplicationError as exc:
            code = str(exc)
            status = 400
            raise HTTPException(status_code=status, detail={"code": code, "message": "Applicant account is invalid"}) from exc

    @router.put("/api/ipo/applications/{ipo_id}/applicants/{owner}/account/remap")
    async def remap_ipo_application_account(ipo_id: str, owner: str, request: Request) -> dict:
        """Explicit, compare-and-swap remap for a previously bound applicant UUID."""
        username = get_current_username(request)
        body = await request.json()
        required = {"broker", "account_id", "expected_current_account_id", "revision"}
        if not isinstance(body, dict) or not required.issubset(body):
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "remap fields are required"})
        broker_id = _validate_ipo_source_broker(ipo_id, body.get("broker"))
        if broker_id is None:
            raise HTTPException(status_code=400, detail={"code": "BROKER_UNKNOWN", "message": "Broker is unknown"})
        from app.services.ipo.applications import (
            ApplicationAccountMappingConflict,
            ApplicationRevisionConflict,
            InvalidApplicationError,
            remap_user_application_account,
        )
        try:
            return remap_user_application_account(
                username, ipo_id, owner, broker_id, body.get("account_id"),
                body.get("expected_current_account_id"), int(body["revision"]),
            )
        except ApplicationRevisionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "REVISION_CONFLICT", "message": str(exc)}) from exc
        except ApplicationAccountMappingConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "MAPPING_CONFLICT", "message": "Applicant account mapping conflicts"}) from exc
        except InvalidApplicationError as exc:
            raise HTTPException(status_code=400, detail={"code": str(exc), "message": "Applicant account is invalid"}) from exc

    @router.put("/api/ipo/applications/{ipo_id}/applicants/{owner}/allocation")
    async def put_ipo_applicant_allocation(ipo_id: str, owner: str, request: Request) -> dict:
        username = get_current_username(request); body = await request.json(); ipo = _ipo_market_record(ipo_id)
        if not isinstance(body, dict) or "quantity" not in body or "revision" not in body:
            raise HTTPException(400, detail={"code": "INVALID_REQUEST", "message": "quantity and revision are required"})
        from app.services.ipo.allocation import AllocationConflict, set_allocation
        from app.services.ipo.applications import ApplicationRevisionConflict, InvalidApplicationError
        try:
            return set_allocation(username, ipo_id, owner, body["quantity"], ipo.get("final_offer_price"), int(body["revision"]))
        except ApplicationRevisionConflict as exc:
            raise HTTPException(409, detail={"code": "REVISION_CONFLICT", "message": str(exc)}) from exc
        except AllocationConflict as exc:
            raise HTTPException(409, detail={"code": str(exc), "message": "Allocation conflicts with linked sales"}) from exc
        except InvalidApplicationError as exc:
            raise HTTPException(400, detail={"code": str(exc), "message": "Allocation is invalid"}) from exc

    @router.get("/api/ipo/applications/{ipo_id}/applicants/{owner}/allocation")
    async def get_ipo_applicant_allocation(ipo_id: str, owner: str, request: Request) -> dict:
        username = get_current_username(request); ipo = _ipo_market_record(ipo_id)
        from app.services.ipo.allocation import allocation_summary
        from app.services.ipo.applications import InvalidApplicationError
        try:
            return allocation_summary(username, ipo_id, owner, str(ipo.get("stock_code") or ""), _ipo_listing_date(ipo))
        except InvalidApplicationError as exc:
            raise HTTPException(400, detail={"code": str(exc), "message": "Allocation is unavailable"}) from exc

    @router.get("/api/ipo/applications/{ipo_id}/applicants/{owner}/allocation/sale-candidates")
    async def get_ipo_allocation_sale_candidates(ipo_id: str, owner: str, request: Request) -> dict:
        username = get_current_username(request); ipo = _ipo_market_record(ipo_id)
        from app.services.ipo.allocation import sale_candidates
        from app.services.ipo.applications import InvalidApplicationError
        try:
            return {"candidates": sale_candidates(username, ipo_id, owner, str(ipo.get("stock_code") or ""), _ipo_listing_date(ipo))}
        except InvalidApplicationError as exc:
            raise HTTPException(400, detail={"code": str(exc), "message": "Sale candidates are unavailable"}) from exc

    @router.post("/api/ipo/applications/{ipo_id}/applicants/{owner}/allocation/links")
    async def link_ipo_applicant_sale(ipo_id: str, owner: str, request: Request) -> dict:
        username = get_current_username(request); body = await request.json(); ipo = _ipo_market_record(ipo_id)
        if not isinstance(body, dict) or not {"pnl_record_id", "matched_quantity", "revision"}.issubset(body):
            raise HTTPException(400, detail={"code": "INVALID_REQUEST", "message": "sale link fields are required"})
        from app.services.ipo.allocation import AllocationConflict, link_sale
        from app.services.ipo.applications import ApplicationRevisionConflict, InvalidApplicationError
        try:
            return link_sale(username, ipo_id, owner, str(body["pnl_record_id"]), body["matched_quantity"], int(body["revision"]), str(ipo.get("stock_code") or ""), _ipo_listing_date(ipo))
        except ApplicationRevisionConflict as exc:
            raise HTTPException(409, detail={"code": "REVISION_CONFLICT", "message": str(exc)}) from exc
        except AllocationConflict as exc:
            raise HTTPException(409, detail={"code": str(exc), "message": "Sale link conflicts"}) from exc
        except InvalidApplicationError as exc:
            raise HTTPException(400, detail={"code": str(exc), "message": "Sale link is invalid"}) from exc

    @router.delete("/api/ipo/applications/{ipo_id}/applicants/{owner}/allocation/links/{pnl_record_id}")
    async def unlink_ipo_applicant_sale(ipo_id: str, owner: str, pnl_record_id: str, request: Request) -> dict:
        """Explicitly remove only an IPO-to-ledger relation after revision validation."""
        username = get_current_username(request)
        body = await request.json()
        if not isinstance(body, dict) or "revision" not in body:
            raise HTTPException(400, detail={"code": "INVALID_REQUEST", "message": "revision is required"})
        from app.services.ipo.allocation import unlink_sale
        from app.services.ipo.applications import ApplicationRevisionConflict, InvalidApplicationError
        try:
            return unlink_sale(username, ipo_id, owner, pnl_record_id, int(body["revision"]))
        except ApplicationRevisionConflict as exc:
            raise HTTPException(409, detail={"code": "REVISION_CONFLICT", "message": str(exc)}) from exc
        except InvalidApplicationError as exc:
            code = str(exc)
            raise HTTPException(404 if code == "LINK_NOT_FOUND" else 400,
                                detail={"code": code, "message": "Sale link is unavailable"}) from exc

    return router
