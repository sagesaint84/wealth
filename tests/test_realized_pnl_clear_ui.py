from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "app" / "static" / "wealth-income-period-broker-filter.js"


def _source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_bulk_clear_intercepts_generic_handler_before_object_detail_is_stringified():
    source = _source()

    assert "document.addEventListener('click', handleClearAllPnl, true);" in source
    assert "event.stopImmediatePropagation();" in source
    assert "pnlClearErrorMessage(result)" in source
    assert "new Error(pnlClearErrorMessage(result))" in source


def test_bulk_clear_maps_linked_ipo_error_to_actionable_korean_message():
    source = _source()

    assert "PNL_RECORDS_LINKED_TO_IPO" in source
    assert "공모주 매도에 연결된 실현손익이 있어 일괄삭제하지 않았습니다." in source
    assert "공모주 매도 연결을 먼저 해제해 주세요." in source


def test_bulk_clear_warns_that_broker_filter_does_not_scope_global_clear():
    source = _source()

    assert "현재 ${broker} 필터가 선택되어 있지만 일괄삭제는 필터와 관계없이 모든 증권사의 실현손익을 삭제합니다." in source
    assert "fetch('/api/realized-pnl/clear'" in source


def test_bulk_clear_keeps_referential_integrity_failure_as_failure():
    source = _source()

    assert "if (!response.ok) throw new Error(pnlClearErrorMessage(result));" in source
    assert "toast(error?.message || '실현손익 일괄삭제 중 오류가 발생했습니다.', true);" in source
