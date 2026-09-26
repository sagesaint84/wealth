from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"target not found: {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Preserve Naver ETF classification into the dividend summary rows.
replace_once(
    "app/services/web_finance.py",
    '''    return {
        "annual_div": dvd_amt,
        "payout_months": payout_months,
        "div_yield": dvd_yield,
        "div_count": len(payout_months),
    }
''',
    '''    return {
        "annual_div": dvd_amt,
        "payout_months": payout_months,
        "div_yield": dvd_yield,
        "div_count": len(payout_months),
        "is_etf": is_etf,
    }
''',
)
replace_once(
    "app/services/web_finance.py",
    '''            "annual_payout_orig": round(annual_payout_orig, 2),
            "payout_months": payout_months,
        })
''',
    '''            "annual_payout_orig": round(annual_payout_orig, 2),
            "payout_months": payout_months,
            "is_etf": bool(d_info.get("is_etf")),
        })
''',
)

# 2) Run the credential-free KIND ETF overlay after OpenDART enrichment.
replace_once(
    "app/services/dividend_official_sources.py",
    '''    _apply_confirmed_future_overrides(
        summary, holdings, fx_rate=fx_rate, as_of=day
    )
    return summary
''',
    '''    _apply_confirmed_future_overrides(
        summary, holdings, fx_rate=fx_rate, as_of=day
    )
    try:
        from app.services.etf_kind_distributions import (
            enrich_dividend_summary_with_kind_etf_distributions,
        )

        summary = await enrich_dividend_summary_with_kind_etf_distributions(
            summary,
            holdings,
            as_of=day,
            fx_rate=fx_rate,
            client=client,
        )
    except Exception:
        policy = summary.setdefault("forecast_source_policy", {})
        policy["kind_etf_status"] = "kind_enrichment_failed"
    return summary
''',
)

# 3) Surface KIND confirmed ETF overlays in the existing source banner.
replace_once(
    "app/static/wealth-dividend-source.js",
    "    if (source === 'opendart_confirmed_disclosure') return 'OpenDART 확정 공시';\n",
    "    if (source === 'kind_etf_confirmed_overlay') return 'KIND ETF 확정 분배금 반영';\n"
    "    if (source === 'opendart_confirmed_disclosure') return 'OpenDART 확정 공시';\n",
)
replace_once(
    "app/static/wealth-dividend-source.js",
    "    let confirmedOverrideCount = 0;\n",
    "    let confirmedOverrideCount = 0;\n"
    "    let kindEtfConfirmedEventCount = 0;\n"
    "    let kindEtfOverrideCount = 0;\n",
)
replace_once(
    "app/static/wealth-dividend-source.js",
    "      if (source.confirmed_numeric_override === true) confirmedOverrideCount += 1;\n",
    "      if (source.confirmed_numeric_override === true) confirmedOverrideCount += 1;\n"
    "      kindEtfConfirmedEventCount += Number(source.kind_etf_confirmed_event_count || 0);\n"
    "      kindEtfOverrideCount += Number(source.kind_etf_numeric_override_count || 0);\n",
)
replace_once(
    "app/static/wealth-dividend-source.js",
    '''    if (confirmedOverrideCount > 0) {
      pieces.push(`확정 공시 금액 반영 ${confirmedOverrideCount}종목`);
    }
''',
    '''    if (confirmedOverrideCount > 0) {
      pieces.push(`확정 공시 금액 반영 ${confirmedOverrideCount}종목`);
    }
    if (kindEtfConfirmedEventCount > 0) {
      pieces.push(`KIND ETF 확정 분배 이벤트 ${kindEtfConfirmedEventCount}건`);
    }
    if (kindEtfOverrideCount > 0) {
      pieces.push(`KIND ETF 공식금액 반영 ${kindEtfOverrideCount}건`);
    }
''',
)
replace_once(
    "app/static/wealth-dividend-source.js",
    "    const kindUrl = policy.kind_reference_url;\n",
    "    const kindUrl = policy.kind_etf_reference_url || policy.kind_reference_url;\n",
)
replace_once(
    "app/static/wealth-dividend-source.js",
    "      link.textContent = 'KIND 배당정보 ↗';\n",
    "      link.textContent = 'KIND ETF/배당정보 ↗';\n",
)

# 4) Add static wiring guards.
static_path = Path("tests/test_dividend_official_source_static.py")
static_text = static_path.read_text(encoding="utf-8")
insert = '''
    def test_kind_etf_official_overlay_is_wired(self):
        web = (ROOT / "app" / "services" / "web_finance.py").read_text(encoding="utf-8")
        official = (ROOT / "app" / "services" / "dividend_official_sources.py").read_text(
            encoding="utf-8"
        )
        ui = (ROOT / "app" / "static" / "wealth-dividend-source.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('"is_etf": is_etf', web)
        self.assertIn('"is_etf": bool(d_info.get("is_etf"))', web)
        self.assertIn("enrich_dividend_summary_with_kind_etf_distributions", official)
        self.assertIn("kind_etf_confirmed_overlay", ui)
        self.assertIn("kind_etf_numeric_override_count", ui)

'''
marker = '\n\nif __name__ == "__main__":\n'
if insert.strip() not in static_text:
    if marker not in static_text:
        raise SystemExit("static test insertion marker missing")
    static_path.write_text(static_text.replace(marker, "\n" + insert + marker, 1), encoding="utf-8")

# 5) Update continuity docs.
project = Path("docs/PROJECT_STATE.md")
text = project.read_text(encoding="utf-8")
old_state = '''현재 작업 단계는 **Phase 10.5A-4.3 — 미래 배당 확정공시 구조화**입니다.

현재 작업:

- branch: `phase10-5a43-confirmed-dividend-disclosures`
- base: `main`
- 상태: 구현 완료 / 로컬 전체 검증 대기
- 작업 시작 기준 main: `0f5f25a` (PR #23 merge)

A-4.3 목표:

1. OpenDART 배당결정 공시 원문에서 주당배당금·기준일·지급예정일을 구조 검증한다.
2. 제목 매칭만으로 `confirmed_amount=true`를 만들지 않는다.
3. 지급예정일이 없으면 날짜를 추정하거나 생성하지 않는다.
4. 현재 연도 미래 지급월과 기존 예상월이 안전하게 매칭될 때만 확정 금액으로 월별 예상을 교체한다.
5. 원문 조회/파싱 실패 시 기존 Naver/Yahoo/공식 과거 이력 fallback을 유지한다.
'''
new_state = '''현재 작업 단계는 **Phase 10.5A-4.4 — 국내 ETF 분배금 공식 Source 개선**입니다.

현재 작업:

- branch: `phase10-5a44-domestic-etf-official-source`
- base: `main`
- 상태: 구현/검증 중
- 작업 시작 기준 main: `86a07ea` (PR #24 merge)

A-4.4 목표:

1. Naver에서 ETF로 식별된 국내상장 ETF만 KIND 공식 ETF 공시를 추가 조회한다.
2. `ETF이익금분배신고(분배금안내)(일괄공시)` 원문에서 ISIN·기준일·지급예정일·분배금을 구조 검증한다.
3. 기준일 월의 기존 휴리스틱을 공식 지급월/금액으로 이동·교체하여 중복계상을 막는다.
4. 안전하게 매칭되지 않는 공식 이벤트는 증거로만 보관하고 숫자에 자동 추가하지 않는다.
5. KIND 조회 실패 시 기존 Naver/OpenDART/Yahoo forecast를 그대로 유지한다.
6. KIND Source는 별도 API 키나 사용자 secret을 추가하지 않는다.
'''
if old_state not in text:
    raise SystemExit("PROJECT_STATE current block missing")
text = text.replace(old_state, new_state, 1)
text = text.replace(
    '- [ ] 10.5A-4.3 미래 배당 확정공시 구조화 — 진행 중',
    '- [x] 10.5A-4.3 미래 배당 확정공시 구조화 — PR #24 merge (`86a07ea`)\n'
    '- [ ] 10.5A-4.4 국내 ETF 분배금 공식 Source 개선 — 진행 중',
    1,
)
a43_tail = '''7. 원문 다운로드/파싱 실패는 기존 예상 전체 실패로 전파하지 않는다.

### 미국
'''
a44_section = '''7. 원문 다운로드/파싱 실패는 기존 예상 전체 실패로 전파하지 않는다.

A-4.4 KIND ETF 분배금 보강:

1. 기존 Naver integration이 ETF로 확인한 종목만 KIND ETF source 대상이 된다.
2. KIND ETF 검색은 별도 API credential 없이 공개 공시 화면을 사용한다.
3. 검색 결과 제목만으로 확정하지 않고 viewer의 공식 `/external/` 문서에서 대상 ISIN 행을 구조 검증한다.
4. 공식 기준일 월에 기존 휴리스틱 항목이 있으면 그 항목을 제거하고 실제 지급예정월에 공식 분배금으로 이동한다.
5. 기존 양수 forecast에 안전하게 매칭되는 월이 없으면 공식 이벤트는 증거로만 남기고 숫자에는 자동 반영하지 않는다.
6. 공식 Source 장애는 기존 Naver/OpenDART/Yahoo forecast를 실패시키지 않는다.

### 미국
'''
if a43_tail not in text:
    raise SystemExit("PROJECT_STATE A4.3 tail missing")
project.write_text(text.replace(a43_tail, a44_section, 1), encoding="utf-8")

roadmap = Path("docs/ROADMAP.md")
rtext = roadmap.read_text(encoding="utf-8")n