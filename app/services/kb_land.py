from typing import Any
import httpx
import logging

logger = logging.getLogger(__name__)

KB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://kbland.kr/",
    "Origin": "https://kbland.kr",
    "Accept": "application/json, text/plain, */*",
}


def search_kb_complex(keyword: str) -> list[dict[str, Any]]:
    """단지명 키워드로 KB부동산 단지 목록을 검색합니다."""
    clean_kw = keyword.strip()
    if not clean_kw:
        return []

    try:
        with httpx.Client(headers=KB_HEADERS, timeout=6.0) as client:
            # 1단계: 자동완성 키워드 목록 조회
            url_auto = "https://api.kbland.kr/land-complex/serch/autoKywrSerch"
            params_auto = {
                "컬렉션설정명": "COL_AT_JUSO:100;COL_AT_SCHOOL:100;COL_AT_SUBWAY:100;COL_AT_HSCM:100;COL_AT_VILLA:100",
                "검색키워드": clean_kw,
            }
            res_auto = client.get(url_auto, params=params_auto)
            data_auto = res_auto.json().get("dataBody", {}).get("data", [])
            hscm_candidates = []
            if data_auto:
                hscm_candidates = data_auto[0].get("COL_AT_HSCM", [])

            results = []
            seen_complex_nos = set()

            targets = [h.get("textTemp") or clean_kw for h in hscm_candidates[:4]]
            if not targets:
                targets = [clean_kw]

            # 2단계: 각 후보별 통합검색(SRC_HSCM)으로 단지기본일련번호 및 상세 정보 획득
            url_intgra = "https://api.kbland.kr/land-complex/serch/intgraSerch"
            for t_kw in targets:
                params_intgra = {
                    "검색설정명": "SRC_HSCM",
                    "검색키워드": t_kw,
                    "출력갯수": 5,
                    "페이지설정값": 1,
                }
                res_int = client.get(url_intgra, params=params_intgra)
                if res_int.status_code != 200:
                    continue
                hscm_list = res_int.json().get("dataBody", {}).get("data", {}).get("data", {}).get("HSCM", {}).get("data", [])
                for item in hscm_list:
                    c_no = str(item.get("COMPLEX_NO") or "").strip()
                    if not c_no or c_no in seen_complex_nos:
                        continue
                    seen_complex_nos.add(c_no)
                    results.append({
                        "complex_no": c_no,
                        "name": item.get("HSCM_NM") or "",
                        "full_name": item.get("HSCM_NM_EXT") or item.get("HSCM_NM") or "",
                        "address": item.get("NEWADDRESS") or item.get("BUBADDR") or "",
                        "total_households": item.get("THS_NUM") or "",
                    })

            return results
    except Exception as e:
        logger.error(f"Error searching KB Land complex: {e}")
        return []


def get_kb_market_prices(complex_no: str | int, target_area: float | None = None) -> dict[str, Any]:
    """단지기본일련번호(complex_no)의 평형별 KB시세를 조회하고, target_area(전용면적)와 가장 가까운 평형을 매칭합니다."""
    c_no = str(complex_no).strip()
    if not c_no:
        return {"error": "단지 번호가 필요합니다."}

    url = "https://api.kbland.kr/land-complex/complex/mpriByType"
    params = {"단지기본일련번호": c_no}

    try:
        with httpx.Client(headers=KB_HEADERS, timeout=6.0) as client:
            res = client.get(url, params=params)
            if res.status_code != 200:
                return {"error": f"KB부동산 응답 오류 (HTTP {res.status_code})"}
            data = res.json()
            price_list = data.get("dataBody", {}).get("data", [])
            if not price_list:
                return {"error": "해당 단지의 KB시세 정보가 없습니다."}

            types = []
            for p in price_list:
                excl = float(p.get("전용면적") or 0.0)
                supply = float(p.get("공급면적") or 0.0)
                pyung_n = p.get("공급면적평N") or str(round(supply / 3.3058)) if supply > 0 else ""
                t_name = p.get("주택형타입내용") or ""
                
                # KB 가격은 만원 단위 -> 원 단위로 환산
                deal_avg = int(p.get("매매일반거래가") or 0) * 10000
                deal_low = int(p.get("매매하한가") or 0) * 10000
                deal_high = int(p.get("매매상한가") or 0) * 10000
                lease_avg = int(p.get("전세일반거래가") or 0) * 10000
                lease_low = int(p.get("전세하한가") or 0) * 10000
                lease_high = int(p.get("전세상한가") or 0) * 10000

                types.append({
                    "exclusive_area": excl,
                    "supply_area": supply,
                    "pyung": pyung_n,
                    "type_name": t_name,
                    "type_display": f"{pyung_n}평형 (전용 {excl}㎡ / 공급 {supply}㎡{f' {t_name}타입' if t_name else ''})",
                    "deal_avg": deal_avg,
                    "deal_low": deal_low,
                    "deal_high": deal_high,
                    "lease_avg": lease_avg,
                    "lease_low": lease_low,
                    "lease_high": lease_high,
                    "deal_count": int(p.get("매매건수") or 0),
                })

            # target_area(전용면적)와 가장 가까운 평형 찾기
            matched = None
            if target_area and target_area > 0 and types:
                # 1순위: 오차 1.5㎡ 이내
                candidates = [t for t in types if abs(t["exclusive_area"] - target_area) <= 1.5]
                if candidates:
                    matched = min(candidates, key=lambda t: abs(t["exclusive_area"] - target_area))
                else:
                    # 2순위: 전체 중 가장 가까운 것
                    matched = min(types, key=lambda t: abs(t["exclusive_area"] - target_area))
            elif types:
                matched = types[0]

            return {
                "complex_no": c_no,
                "matched": matched,
                "types": types,
            }
    except Exception as e:
        logger.error(f"Error getting KB market prices: {e}")
        return {"error": f"시세 조회 중 오류 발생: {str(e)}"}
