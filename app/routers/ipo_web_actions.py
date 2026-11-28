from __future__ import annotations

import html
from types import ModuleType
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


ACTION_LANDING_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="referrer" content="no-referrer" />
<title>{{page_title}} - Wealth Action</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:radial-gradient(ellipse at 50% 20%, #15102a 0%, #060913 70%); color:#e0e6f5;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .card { width:100%; max-width:440px; padding:32px 28px; border-radius:16px; box-sizing:border-box;
          background:rgba(14,21,41,0.96); border:1px solid #3d2c73;
          box-shadow:0 20px 50px rgba(0,0,0,0.7), 0 0 0 1px rgba(157,123,255,0.2); backdrop-filter:blur(10px); }
  .brand-wrap { display:flex; align-items:center; gap:12px; margin-bottom:20px; }
  .brand-icon { width:36px; height:36px; border-radius:10px; background:linear-gradient(135deg,#9d7bff,#5d3ad4);
                display:flex; align-items:center; justify-content:center; font-weight:800; font-size:18px; color:#fff; }
  h1 { font-size:20px; font-weight:800; margin:0; color:#f3f5ff; }
  .desc { font-size:14px; color:#91a0c1; line-height:1.5; margin:0 0 20px; }
  .info-box { background:#080e1e; border:1px solid #222d48; border-radius:10px; padding:16px; margin-bottom:24px; }
  .info-row { display:flex; justify-content:space-between; margin-bottom:8px; font-size:13.5px; }
  .info-row:last-child { margin-bottom:0; }
  .info-label { color:#7e8ea8; }
  .info-value { color:#f3f5ff; font-weight:600; }
  .status-badge { display:inline-block; padding:3px 8px; border-radius:6px; font-size:12px; font-weight:700; }
  .badge-pending { background:rgba(157,123,255,0.18); color:#c4b5fd; border:1px solid rgba(157,123,255,0.3); }
  .badge-done { background:rgba(34,197,94,0.18); color:#86efac; border:1px solid rgba(34,197,94,0.3); }
  .badge-error { background:rgba(239,68,68,0.18); color:#fca5a5; border:1px solid rgba(239,68,68,0.3); }
  button { width:100%; padding:13px; border:none; border-radius:10px;
           background:linear-gradient(135deg,#8e70fa,#5d3ad4); color:white; font-size:15px; font-weight:700; cursor:pointer;
           box-shadow:0 6px 18px rgba(93,58,212,0.4); transition:.18s; }
  button:hover { filter:brightness(1.12); transform:translateY(-1px); }
  .back-link { display:block; text-align:center; margin-top:16px; font-size:13px; color:#91a0c1; text-decoration:none; }
  .back-link:hover { color:#c4b5fd; }
</style>
</head>
<body>
  <div class="card">
    <div class="brand-wrap">
      <div class="brand-icon">W</div>
      <h1>{{header_title}}</h1>
    </div>
    <p class="desc">{{description}}</p>
    <div class="info-box">
      {{info_rows}}
    </div>
    {{action_content}}
    <a href="/dashboard" class="back-link">대시보드로 돌아가기</a>
  </div>
</body>
</html>"""


def _render_action_card(
    *,
    page_title: str,
    header_title: str,
    description: str,
    info_dict: dict[str, str],
    action_content: str,
    status_code: int = 200,
) -> HTMLResponse:
    info_rows = ""
    for k, v in info_dict.items():
        info_rows += f'<div class="info-row"><span class="info-label">{html.escape(k)}</span><span class="info-value">{html.escape(v)}</span></div>'
    rendered = (
        ACTION_LANDING_HTML
        .replace("{{page_title}}", html.escape(page_title))
        .replace("{{header_title}}", html.escape(header_title))
        .replace("{{description}}", html.escape(description))
        .replace("{{info_rows}}", info_rows)
        .replace("{{action_content}}", action_content)
    )
    return HTMLResponse(
        content=rendered,
        status_code=status_code,
        headers={"Referrer-Policy": "no-referrer"},
    )


def _validate_same_origin_request(request: Request) -> bool:
    """Strict same-origin CSRF validation against configured public_base_url.

    Checks Origin (or Referer as fallback). Both must match configured public_base_url origin.
    Missing Origin AND missing Referer fails closed (returns False).
    """
    from app.services.system_settings import get_effective_system_settings
    settings = get_effective_system_settings()
    base_url = settings.get("public_base_url")
    if not base_url:
        return False

    try:
        base_parts = urlsplit(base_url)
        expected_scheme = base_parts.scheme
        expected_netloc = base_parts.netloc
    except Exception:
        return False

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    if origin:
        try:
            o_parts = urlsplit(origin)
            return o_parts.scheme == expected_scheme and o_parts.netloc == expected_netloc
        except Exception:
            return False

    if referer:
        try:
            r_parts = urlsplit(referer)
            return r_parts.scheme == expected_scheme and r_parts.netloc == expected_netloc
        except Exception:
            return False

    return False


def _fmt_qty(n: object) -> str:
    try:
        return f"{int(n):,}주"
    except Exception:
        return "-"


def _fmt_krw(n: object) -> str:
    try:
        v = int(float(str(n)))
        sign = "+" if v > 0 else ""
        return f"{sign}{v:,}원"
    except Exception:
        return "-"


def create_ipo_web_actions_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/a/{token}", include_in_schema=False)
    async def get_web_action_landing(request: Request, token: str) -> HTMLResponse:
        from app.services.action_v2 import (
            ACTION_TYPE_MARK_IPO_APPLIED,
            ACTION_TYPE_OPEN_IPO_SALE_FLOW,
            get_web_action_metadata,
            is_action_expired,
            validate_action_token,
        )
        from app.services.ipo.applications import get_user_applications
        from app.services.ipo.store import read_market_store_read_only

        try:
            token = validate_action_token(token)
        except Exception:
            return runtime._render_action_card(
                page_title="유효하지 않은 링크",
                header_title="작업 링크 오류",
                description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                info_dict={"상태": "유효하지 않음"},
                action_content="",
                status_code=404,
            )

        current_user = runtime.get_current_username(request)
        action = get_web_action_metadata(token)
        if not action:
            return runtime._render_action_card(
                page_title="유효하지 않은 링크",
                header_title="작업 링크 오류",
                description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                info_dict={"상태": "유효하지 않음"},
                action_content="",
                status_code=404,
            )

        # Cross-user authorization check: strict username binding
        if action.get("username") != current_user:
            return runtime._render_action_card(
                page_title="접근 제한",
                header_title="접근 권한 없음",
                description="해당 작업에 대한 접근 권한이 없습니다. 올바른 계정으로 로그인해 주세요.",
                info_dict={"요청 계정": current_user},
                action_content="",
                status_code=403,
            )

        action_type = action.get("action_type")
        meta = action.get("metadata", {})
        ipo_id = meta.get("ipo_id")
        owner = meta.get("owner") or "-"

        # Canonical IPO display resolve: authoritative source is read_market_store_read_only()
        ipo_name = "공모주"
        matched_ipo = None
        if ipo_id:
            try:
                market_ipos = read_market_store_read_only().get("ipos", [])
                matched_ipo = next((x for x in market_ipos if x.get("ipo_id") == ipo_id), None)
                if matched_ipo and matched_ipo.get("company_name"):
                    ipo_name = matched_ipo["company_name"]
                elif matched_ipo and matched_ipo.get("name"):
                    ipo_name = matched_ipo["name"]
            except Exception as exc:
                runtime.logger.warning("Failed to resolve canonical IPO company name: %s", type(exc).__name__)

        # Expiration check
        if is_action_expired(action):
            return runtime._render_action_card(
                page_title="만료된 링크",
                header_title="작업 기한 만료",
                description="해당 청약 신청 기한이 이미 만료되었습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "상태": "기한 만료",
                },
                action_content="",
                status_code=410,
            )

        # Already consumed check
        if action.get("consumed_at"):
            return runtime._render_action_card(
                page_title="처리 완료된 작업",
                header_title="이미 처리된 작업",
                description="해당 작업은 이미 성공적으로 처리되었습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "처리 상태": "완료됨",
                },
                action_content="",
                status_code=200,
            )

        # Check live application state
        apps = get_user_applications(current_user)
        app_record = apps.get("applications", {}).get(ipo_id, {})
        applied_owners = list(app_record.get("applied_owners") or [])
        if action_type == ACTION_TYPE_MARK_IPO_APPLIED and owner in applied_owners:
            return runtime._render_action_card(
                page_title="청약 완료 상태",
                header_title="청약 신청 완료 확인",
                description="해당 대상자는 이미 청약 완료 상태로 등록되어 있습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "현재 상태": "청약 완료",
                },
                action_content="",
                status_code=200,
            )

        if action_type == ACTION_TYPE_MARK_IPO_APPLIED:
            action_button = f"""<form method="post" action="/a/{runtime.html.escape(token)}/execute">
          <button type="submit">청약 완료 확인 및 상태 변경</button>
        </form>"""
            return runtime._render_action_card(
                page_title="청약 완료 확인",
                header_title="IPO 청약 완료 확인",
                description="아래 정보를 확인하고 청약 완료 처리를 진행해 주세요.",
                info_dict={
                    "종목명": ipo_name,
                    "신청 대상": owner,
                    "현재 상태": "청약 전 (확인 대기)",
                },
                action_content=action_button,
                status_code=200,
            )
        elif action_type == ACTION_TYPE_OPEN_IPO_SALE_FLOW:
            from app.services.ipo.allocation import allocation_summary, sale_candidates
            from app.services.ipo.applications import InvalidApplicationError

            # Metadata contains only opaque authoritative identifiers.  Resolve
            # mutable market facts from the canonical market store on every view.
            stock_code = str((matched_ipo or {}).get("stock_code") or "")
            listing_date = str(
                (matched_ipo or {}).get("actual_listing_date")
                or (matched_ipo or {}).get("expected_listing_date")
                or ""
            )[:10] or None

            # Resolve account mapping before allocation state so that an applied
            # owner with no bound account is distinct from a mapped owner whose
            # allocation quantity has not been recorded yet.
            applicant = (app_record.get("applicants") or {}).get(owner)
            account_resolved = (
                isinstance(applicant, dict)
                and bool(applicant.get("broker_id"))
                and bool(applicant.get("account_id"))
            )
            alloc_status = "UNRESOLVED_ACCOUNT" if not account_resolved else None
            alloc_data = None
            candidates: list[dict] = []
            alloc_error: str | None = None
            if account_resolved:
                try:
                    summary = allocation_summary(current_user, ipo_id, owner, stock_code, listing_date)
                    alloc_status = summary.get("status")
                    alloc_data = summary.get("allocation")
                    if alloc_status in ("UNSOLD", "PARTIALLY_SOLD"):
                        candidates = sale_candidates(current_user, ipo_id, owner, stock_code, listing_date)
                except InvalidApplicationError:
                    # Canonical application/allocation state is unavailable.  Do
                    # not offer a mutation form from an ambiguous state.
                    alloc_error = "DATA_UNAVAILABLE"
                except Exception as exc:
                    runtime.logger.warning(
                        "IPO allocation summary unavailable in GET handler: %s",
                        type(exc).__name__,
                    )
                    alloc_error = "DATA_UNAVAILABLE"

            if alloc_status == "FULLY_SOLD":
                return runtime._render_action_card(
                    page_title="매도 기록 완료",
                    header_title="매도 기록 완료",
                    description="해당 배정 물량이 전량 매도 처리 완료되었습니다.",
                    info_dict={
                        "종목명": ipo_name,
                        "대상자": owner,
                        "배정수량": _fmt_qty(alloc_data.get("quantity") if alloc_data else None),
                        "상태": "전량 매도 완료",
                    },
                    action_content="",
                    status_code=200,
                )


            if alloc_status == "UNRESOLVED_ACCOUNT":
                return runtime._render_action_card(
                    page_title="계좌 연결 필요",
                    header_title="청약 계좌 연결 필요",
                    description="매도 기록을 연결하려면 먼저 청약 계좌를 연결해 주세요.",
                    info_dict={
                        "종목명": ipo_name,
                        "대상자": owner,
                        "상태": "청약 계좌 연결 필요",
                    },
                    action_content="",
                    status_code=200,
                )

            if alloc_status == "NO_ALLOCATION":
                return runtime._render_action_card(
                    page_title="배정 없음",
                    header_title="배정 0주",
                    description="해당 공모주 청약 결과 배정이 이루어지지 않았습니다.",
                    info_dict={
                        "종목명": ipo_name,
                        "대상자": owner,
                        "배정수량": "0주",
                        "상태": "미배정",
                    },
                    action_content="",
                    status_code=200,
                )

            if alloc_status == "UNRESOLVED":
                return runtime._render_action_card(
                    page_title="배정 미기록",
                    header_title="배정수량 미기록",
                    description="배정수량이 아직 기록되지 않았습니다. Wealth에서 배정수량을 먼저 입력해 주세요.",
                    info_dict={
                        "종목명": ipo_name,
                        "대상자": owner,
                        "상태": "배정수량 미기록",
                    },
                    action_content="",
                    status_code=200,
                )

            if alloc_error:
                return runtime._render_action_card(
                    page_title="상태 확인 필요",
                    header_title="매도 기록 상태 확인 필요",
                    description="현재 배정 및 매도 연결 상태를 안전하게 확인할 수 없습니다. Wealth에서 상태를 확인해 주세요.",
                    info_dict={"종목명": ipo_name, "대상자": owner, "상태": "확인 필요"},
                    action_content="",
                    status_code=409,
                )

            if alloc_status == "LINK_DATA_MISSING":
                return runtime._render_action_card(
                    page_title="데이터 확인 필요",
                    header_title="매도 연결 데이터 오류",
                    description="기존 매도 연결 데이터 확인이 필요합니다. Wealth에서 연결된 실현손익 기록을 확인해 주세요.",
                    info_dict={
                        "종목명": ipo_name,
                        "대상자": owner,
                        "배정수량": _fmt_qty(alloc_data.get("quantity") if alloc_data else None),
                        "상태": "LINK_DATA_MISSING",
                    },
                    action_content="",
                    status_code=200,
                )

            # UNSOLD or PARTIALLY_SOLD — show form with candidates
            sold_qty = alloc_data.get("sold_quantity", 0) if alloc_data else 0
            remaining_qty = alloc_data.get("remaining_quantity", 0) if alloc_data else 0
            total_qty = alloc_data.get("quantity", 0) if alloc_data else 0

            if not candidates:
                form_html = (
                    "<p style='font-size:13px;color:#91a0c1;text-align:center;margin:0'>"
                "연결 가능한 매도 실현손익 기록이 없습니다.</p>"
                )
            else:
                candidate_options = ""
                for c in candidates:
                    pnl_id = runtime.html.escape(str(c.get("pnl_record_id", "")))
                    date_str = runtime.html.escape(str(c.get("date") or "-"))
                    avail = c.get("available_quantity", 0)
                    pnl_krw = c.get("pnl_krw")
                    pnl_label = _fmt_krw(pnl_krw)
                    candidate_options += (
                        f'<option value="{pnl_id}" data-avail="{avail}">'
                    f'{date_str} | 가능수량 {avail:,}주 | 실현손익 {pnl_label}'
                    f'</option>\n'
                    )
                esc_token = runtime.html.escape(token)
                form_html = f"""<form method="post" action="/a/{esc_token}/link-sale" id="lsform"
  style="display:flex;flex-direction:column;gap:12px;margin-top:4px">
  <div>
    <label style="font-size:12px;color:#7e8ea8;display:block;margin-bottom:4px">매도 실현손익 기록 선택</label>
    <select name="pnl_record_id" id="pnl_sel" required
      style="width:100%;padding:10px;border-radius:8px;border:1px solid #3d2c73;
             background:#080e1e;color:#f3f5ff;font-size:13px;box-sizing:border-box">
      <option value="">— 기록 선택 —</option>
      {candidate_options}
    </select>
  </div>
  <div>
    <label style="font-size:12px;color:#7e8ea8;display:block;margin-bottom:4px">
      연결 수량 <span id="avail_hint" style="color:#c4b5fd"></span>
    </label>
    <input name="matched_quantity" id="qty_inp" type="number" min="1" max="{remaining_qty}" required
      placeholder="수량 입력"
      style="width:100%;padding:10px;border-radius:8px;border:1px solid #3d2c73;
             background:#080e1e;color:#f3f5ff;font-size:13px;box-sizing:border-box" />
  </div>
  <button type="submit">매도 기록 연결</button>
</form>
<script>
(function(){{
  var sel=document.getElementById('pnl_sel');
  var inp=document.getElementById('qty_inp');
  var hint=document.getElementById('avail_hint');
  sel.addEventListener('change',function(){{
    var opt=sel.options[sel.selectedIndex];
    var avail=opt.getAttribute('data-avail');
    if(avail){{hint.textContent='(가능 '+parseInt(avail,10).toLocaleString()+'주)';inp.max=avail;inp.value='';}}
    else{{hint.textContent='';inp.max='{remaining_qty}';}}
  }});
}})();
</script>"""

            status_label = "매도 전" if alloc_status == "UNSOLD" else f"일부 매도 ({sold_qty:,}주/{total_qty:,}주)"
            return runtime._render_action_card(
                page_title="매도 기록 연결",
                header_title="IPO 상장일 매도 기록",
                description="아래에서 실현손익 기록을 선택하고 연결 수량을 입력해 주세요.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "배정수량": _fmt_qty(total_qty),
                    "잔여수량": _fmt_qty(remaining_qty),
                    "상태": status_label,
                },
                action_content=form_html,
                status_code=200,
            )
        else:
            return runtime._render_action_card(
                page_title="지원하지 않는 작업",
                header_title="알 수 없는 작업",
                description="지원되지 않는 작업 유형입니다.",
                info_dict={"작업 유형": str(action_type)},
                action_content="",
                status_code=400,
            )

    @router.post("/a/{token}/execute", include_in_schema=False)
    async def post_web_action_execute(request: Request, token: str) -> HTMLResponse:
        from app.services.action_v2 import execute_web_action, validate_action_token
        from app.services.ipo.actions import IpoActionError

        # 1. CSRF same-origin check
        if not runtime._validate_same_origin_request(request):
            return runtime._render_action_card(
                page_title="접근 제한",
                header_title="요청 검증 실패",
                description="안전하지 않거나 허용되지 않은 출처에서의 요청입니다.",
                info_dict={"오류": "CSRF_FORBIDDEN"},
                action_content="",
                status_code=403,
            )

        # 2. Token format validation
        try:
            token = validate_action_token(token)
        except Exception:
            return runtime._render_action_card(
                page_title="유효하지 않은 링크",
                header_title="작업 링크 오류",
                description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                info_dict={"상태": "유효하지 않음"},
                action_content="",
                status_code=404,
            )

        current_user = runtime.get_current_username(request)
        try:
            result = execute_web_action(token, authenticated_username=current_user)
        except IpoActionError as exc:
            err_msg = str(exc)
            if err_msg == "ACTION_NOT_FOUND":
                return runtime._render_action_card(
                    page_title="유효하지 않은 링크",
                    header_title="작업 링크 오류",
                    description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                    info_dict={"상태": "유효하지 않음"},
                    action_content="",
                    status_code=404,
                )
            elif err_msg == "FORBIDDEN":
                return runtime._render_action_card(
                    page_title="접근 제한",
                    header_title="접근 권한 없음",
                    description="해당 작업에 대한 접근 권한이 없습니다. 올바른 계정으로 로그인해 주세요.",
                    info_dict={"요청 계정": current_user},
                    action_content="",
                    status_code=403,
                )
            elif err_msg == "ACTION_EXPIRED":
                return runtime._render_action_card(
                    page_title="만료된 링크",
                    header_title="작업 기한 만료",
                    description="해당 청약 신청 기한이 이미 만료되었습니다.",
                    info_dict={"상태": "기한 만료"},
                    action_content="",
                    status_code=410,
                )
            elif err_msg == "ACTION_NOT_EXECUTABLE":
                return runtime._render_action_card(
                    page_title="실행 불가",
                    header_title="실행할 수 없는 작업",
                    description="해당 작업은 현재 웹 액션으로 실행할 수 없습니다.",
                    info_dict={"상태": "ACTION_NOT_EXECUTABLE"},
                    action_content="",
                    status_code=400,
                )
            elif err_msg in (
                "ACTION_ALREADY_RUNNING",
                "ACTION_V2_STATE_INVALID",
                "ACTION_TOKEN_INVALID",
                "SUBSCRIPTION_NOT_ACTIVE",
                "OWNER_NOT_ELIGIBLE",
                "IPO_NOT_FOUND",
            ):
                # Known stable business error codes
                safe_descriptions = {
                    "ACTION_ALREADY_RUNNING": "다른 작업이 처리 중입니다. 잠시 후 다시 시도해 주세요.",
                    "ACTION_V2_STATE_INVALID": "작업 저장소 상태를 확인할 수 없습니다.",
                    "ACTION_TOKEN_INVALID": "유효하지 않은 요청 토큰입니다.",
                    "SUBSCRIPTION_NOT_ACTIVE": "청약 진행 기간이 아닙니다.",
                    "OWNER_NOT_ELIGIBLE": "해당 청약의 신청 대상자가 아닙니다.",
                    "IPO_NOT_FOUND": "대상 공모주 정보를 찾을 수 없습니다.",
                }
                desc = safe_descriptions.get(err_msg, "작업을 처리할 수 없습니다.")
                return runtime._render_action_card(
                    page_title="처리 실패",
                    header_title="작업 처리 실패",
                    description=desc,
                    info_dict={"상태": err_msg},
                    action_content="",
                    status_code=400,
                )
            else:
                runtime.logger.warning("Action execution failed with unmapped error: %s", err_msg)
                return runtime._render_action_card(
                    page_title="처리 실패",
                    header_title="작업 처리 실패",
                    description="작업을 처리할 수 없습니다.",
                    info_dict={"상태": "ERROR"},
                    action_content="",
                    status_code=400,
                )

        status = result.get("status")
        owner = result.get("owner", "")
        if status == "already_applied":
            return runtime._render_action_card(
                page_title="청약 완료",
                header_title="이미 처리 완료",
                description=f"{owner} 님의 청약 완료 처리가 이미 반영되어 있습니다.",
                info_dict={"대상자": owner, "처리 결과": "기 반영됨"},
                action_content="",
                status_code=200,
            )
        elif status == "already_processed":
            return runtime._render_action_card(
                page_title="처리 완료",
                header_title="이미 처리 완료",
                description="해당 작업 링크는 이미 처리되었습니다.",
                info_dict={"처리 결과": "이미 처리됨"},
                action_content="",
                status_code=200,
            )
        elif status == "applied":
            notification_status = result.get("notification", {}).get("status")
            confirmation_info = {}
            if notification_status in {"failed", "partial", "unconfigured"}:
                confirmation_info["확인 알림"] = "일부 알림을 보내지 못했습니다. 청약 완료 기록은 저장되었습니다."
            return runtime._render_action_card(
                page_title="청약 완료 완료",
                header_title="청약 완료 처리 성공",
                description=f"축하합니다! {owner} 님의 공모주 청약이 성공적으로 완료 처리되었습니다.",
                info_dict={"대상자": owner, "처리 결과": "청약 완료 등록 성공", **confirmation_info},
                action_content="",
                status_code=200,
            )
        else:
            return runtime._render_action_card(
                page_title="작업 완료",
                header_title="작업 처리 완료",
                description="작업이 성공적으로 처리되었습니다.",
                info_dict={"처리 결과": "완료"},
                action_content="",
                status_code=200,
            )

    @router.post("/a/{token}/link-sale", include_in_schema=False)
    async def post_web_action_link_sale(request: Request, token: str) -> HTMLResponse:
        """Link a P&L record to an IPO allocation (OPEN_IPO_SALE_FLOW)."""
        from app.services.action_v2 import (
            ACTION_TYPE_OPEN_IPO_SALE_FLOW,
            get_web_action_metadata,
            is_action_expired,
            mark_web_action_consumed_if_current,
            validate_action_token,
        )
        from app.services.ipo.allocation import (
            AllocationConflict,
            allocation_summary,
            link_sale,
        )
        from app.services.ipo.applications import (
            ApplicationRevisionConflict,
            InvalidApplicationError,
            get_user_applications,
        )
        from app.services.ipo.store import read_market_store_read_only

        # 1. CSRF same-origin check
        if not runtime._validate_same_origin_request(request):
            return runtime._render_action_card(
                page_title="접근 제한",
                header_title="요청 검증 실패",
                description="안전하지 않거나 허용되지 않은 출처에서의 요청입니다.",
                info_dict={"오류": "CSRF_FORBIDDEN"},
                action_content="",
                status_code=403,
            )

        # 2. Token format validation
        try:
            token = validate_action_token(token)
        except Exception:
            return runtime._render_action_card(
                page_title="유효하지 않은 링크",
                header_title="작업 링크 오류",
                description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                info_dict={"상태": "유효하지 않음"},
                action_content="",
                status_code=404,
            )

        current_user = runtime.get_current_username(request)
        action = get_web_action_metadata(token)
        if not action:
            return runtime._render_action_card(
                page_title="유효하지 않은 링크",
                header_title="작업 링크 오류",
                description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                info_dict={"상태": "유효하지 않음"},
                action_content="",
                status_code=404,
            )

        # 3. Cross-user authorization
        if action.get("username") != current_user:
            return runtime._render_action_card(
                page_title="접근 제한",
                header_title="접근 권한 없음",
                description="해당 작업에 대한 접근 권한이 없습니다. 올바른 계정으로 로그인해 주세요.",
                info_dict={"요청 계정": current_user},
                action_content="",
                status_code=403,
            )

        # 4. Action type guard — only OPEN_IPO_SALE_FLOW handled here
        if action.get("action_type") != ACTION_TYPE_OPEN_IPO_SALE_FLOW:
            return runtime._render_action_card(
                page_title="지원하지 않는 작업",
                header_title="알 수 없는 작업",
                description="지원되지 않는 작업 유형입니다.",
                info_dict={"작업 유형": str(action.get("action_type"))},
                action_content="",
                status_code=400,
            )

        # 5. Expiry check
        if is_action_expired(action):
            return runtime._render_action_card(
                page_title="만료된 링크",
                header_title="작업 기한 만료",
                description="해당 상장일 매도 기록 기한이 이미 만료되었습니다.",
                info_dict={"상태": "기한 만료"},
                action_content="",
                status_code=410,
            )

        meta = action.get("metadata", {})
        ipo_id = meta.get("ipo_id") or ""
        owner = meta.get("owner") or ""
        stock_code = ""
        listing_date = None

        # Resolve canonical IPO name for display
        ipo_name = "공모주"
        matched_ipo = None
        try:
            market_ipos = read_market_store_read_only().get("ipos", [])
            matched_ipo = next((x for x in market_ipos if x.get("ipo_id") == ipo_id), None)
            if matched_ipo and matched_ipo.get("company_name"):
                ipo_name = matched_ipo["company_name"]
            elif matched_ipo and matched_ipo.get("name"):
                ipo_name = matched_ipo["name"]
            if isinstance(matched_ipo, dict):
                stock_code = str(matched_ipo.get("stock_code") or "")
                listing_date = str(
                    matched_ipo.get("actual_listing_date")
                    or matched_ipo.get("expected_listing_date")
                    or ""
                )[:10] or None
        except Exception as exc:
            runtime.logger.warning("Failed to resolve canonical IPO company name: %s", type(exc).__name__)

        if not isinstance(matched_ipo, dict) or not stock_code or not listing_date:
            return runtime._render_action_card(
                page_title="연결 실패",
                header_title="매도 기록 연결 실패",
                description="상장 종목 정보를 확인할 수 없습니다.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "오류"},
                action_content="",
                status_code=400,
            )

        # Re-resolve current application/account state.  The action was valid at
        # creation time, but a stale link must not bypass current owner/account
        # eligibility.
        current_apps = get_user_applications(current_user)
        current_app = (current_apps.get("applications") or {}).get(ipo_id, {})
        if owner not in list(current_app.get("applied_owners") or []):
            return runtime._render_action_card(
                page_title="연결 실패",
                header_title="매도 기록 연결 불가",
                description="현재 청약 신청 상태를 확인해 주세요.",
                info_dict={"종목명": ipo_name, "상태": "OWNER_NOT_ELIGIBLE"},
                action_content="",
                status_code=400,
            )
        current_applicant = (current_app.get("applicants") or {}).get(owner)
        if (
            not isinstance(current_applicant, dict)
            or not current_applicant.get("broker_id")
            or not current_applicant.get("account_id")
        ):
            return runtime._render_action_card(
                page_title="계좌 연결 필요",
                header_title="청약 계좌 연결 필요",
                description="매도 기록을 연결하려면 먼저 청약 계좌를 연결해 주세요.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "UNRESOLVED_ACCOUNT"},
                action_content="",
                status_code=400,
            )

        # A stale action must never create an additional link.  FULLY_SOLD is
        # derived from allocation links; consume the URL lifecycle only now.
        try:
            pre_status = allocation_summary(current_user, ipo_id, owner, stock_code, listing_date).get("status")
        except InvalidApplicationError:
            pre_status = "UNRESOLVED"
        if pre_status == "FULLY_SOLD":
            try:
                mark_web_action_consumed_if_current(
                    token, authenticated_username=current_user,
                    action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                )
            except Exception as exc:
                runtime.logger.warning("Failed to consume stale fully-sold action: %s", type(exc).__name__)
            return runtime._render_action_card(
                page_title="매도 기록 완료", header_title="매도 기록 완료",
                description="해당 배정 물량이 전량 매도 처리 완료되었습니다.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "전량 매도 완료"},
                action_content="", status_code=200,
            )
        if pre_status == "LINK_DATA_MISSING":
            return runtime._render_action_card(
                page_title="연결 실패", header_title="매도 연결 데이터 오류",
                description="기존 매도 연결 데이터를 먼저 확인해 주세요.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "IPO_LINK_DATA_MISSING"},
                action_content="", status_code=409,
            )
        if pre_status in {"NO_ALLOCATION", "UNRESOLVED"}:
            return runtime._render_action_card(
                page_title="연결 실패", header_title="매도 기록 연결 불가",
                description="배정수량 기록을 먼저 확인해 주세요.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": pre_status},
                action_content="", status_code=400,
            )

        # 6. Parse POST body
        try:
            form = await request.form()
            pnl_record_id = str(form.get("pnl_record_id") or "").strip()
            matched_quantity_raw = str(form.get("matched_quantity") or "").strip()
            if not pnl_record_id:
                raise ValueError("pnl_record_id is required")
            matched_quantity = int(matched_quantity_raw)
            if matched_quantity <= 0:
                raise ValueError("matched_quantity must be positive")
        except (ValueError, TypeError) as exc:
            return runtime._render_action_card(
                page_title="입력 오류",
                header_title="입력값 오류",
                description="입력값을 확인해 주세요.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "입력 오류"},
                action_content="",
                status_code=400,
            )

        # 7. CAS retry loop: read revision → link_sale → retry on conflict (up to 3)
        MAX_RETRIES = 3
        last_error: Exception | None = None
        link_result: dict | None = None
        for attempt in range(MAX_RETRIES):
            try:
                revision = int(get_user_applications(current_user)["revision"])
                link_result = link_sale(
                    username=current_user,
                    ipo_id=ipo_id,
                    owner=owner,
                    pnl_record_id=pnl_record_id,
                    matched_quantity=matched_quantity,
                    revision=revision,
                    stock_code=stock_code,
                    listing_date=listing_date,
                )
                break
            except ApplicationRevisionConflict:
                last_error = None  # retry
                continue
            except (InvalidApplicationError, AllocationConflict) as exc:
                last_error = exc
                break
            except Exception as exc:
                runtime.logger.warning("link_sale unexpected error: %s", type(exc).__name__)
                last_error = exc
                break
        else:
            last_error = RuntimeError("REVISION_CONFLICT_EXHAUSTED")

        if last_error is not None:
            err_str = str(last_error)
            user_messages = {
                "IPO application must be saved before allocation": "신청 정보가 없습니다. Wealth에서 청약 신청 정보를 확인해 주세요.",
                "Applicant account must be connected before allocation": "증권사 계좌 연결이 필요합니다.",
                "ALLOCATION_REQUIRED": "배정수량 기록이 필요합니다.",
                "PNL_RECORD_NOT_FOUND": "선택한 실현손익 기록을 찾을 수 없습니다.",
                "IPO_SALE_MATCH_INELIGIBLE": "선택한 기록이 이 종목·계좌 조건에 맞지 않습니다.",
                "ALLOCATION_BELOW_LINKED_QUANTITY": "배정수량보다 연결 수량이 많습니다.",
                "DUPLICATE_LINK_CONFLICT": "이미 동일한 기록이 연결되어 있습니다.",
                "ALLOCATION_OVERRUN": "연결 수량이 잔여 배정수량을 초과합니다.",
                "PNL_OVERRUN": "해당 실현손익 기록의 수량이 초과됩니다.",
                "REVISION_CONFLICT_EXHAUSTED": "동시 요청 충돌이 반복되었습니다. 잠시 후 다시 시도해 주세요.",
            }
            desc = user_messages.get(err_str, "처리 중 오류가 발생했습니다. Wealth에서 상태를 확인한 뒤 다시 시도해 주세요.")
            return runtime._render_action_card(
                page_title="연결 실패",
                header_title="매도 기록 연결 실패",
                description=desc,
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "오류"},
                action_content="",
                status_code=400,
            )

        # 8. Check post-link allocation status to decide if action is fully consumed
        new_status = "UNSOLD"
        try:
            new_summary = allocation_summary(current_user, ipo_id, owner, stock_code, listing_date)
            new_status = new_summary.get("status", "UNSOLD")
        except Exception as exc:
            runtime.logger.warning("allocation_summary after link_sale failed: %s", type(exc).__name__)

        if new_status == "FULLY_SOLD":
            # Action lifecycle is separate from the allocation/P&L authority.
            try:
                mark_web_action_consumed_if_current(
                    token,
                    authenticated_username=current_user,
                    action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                )
            except Exception as exc:
                runtime.logger.warning("Failed to mark action consumed after FULLY_SOLD: %s", type(exc).__name__)

        # 9. Render success card
        link_status = (link_result or {}).get("status", "LINKED")
        if link_status == "IDEMPOTENT":
            return runtime._render_action_card(
                page_title="이미 연결됨",
                header_title="중복 연결 감지",
                description="동일한 수량과 기록이 이미 연결되어 있습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "연결 수량": f"{matched_quantity:,}주",
                    "상태": "기 연결됨 (변경 없음)",
                },
                action_content="",
                status_code=200,
            )

        if new_status == "FULLY_SOLD":
            return runtime._render_action_card(
                page_title="매도 기록 완료",
                header_title="전량 매도 기록 완료",
                description="배정 수량 전체가 매도 기록으로 연결되었습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "연결 수량": f"{matched_quantity:,}주",
                    "상태": "전량 매도 완료",
                },
                action_content="",
                status_code=200,
            )

        # PARTIALLY_SOLD — still has remaining quantity
        return runtime._render_action_card(
            page_title="매도 기록 연결 완료",
            header_title="매도 기록 연결 완료",
            description="매도 기록이 연결되었습니다. 잔여 수량이 남아 있으면 추가 연결이 가능합니다.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "연결 수량": f"{matched_quantity:,}주",
                "상태": "일부 연결 완료",
            },
            action_content=f'<a href="/a/{runtime.html.escape(token)}" style="display:block;text-align:center;margin-top:8px;font-size:14px;color:#c4b5fd">추가 연결하기 →</a>',
            status_code=200,
        )

    return router
