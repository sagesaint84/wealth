# Wealth 시장심리 지표 데이터 출처·산식 계약 검토 (2026-10-25)

> 상태: RESEARCH ONLY / SCORE DATA NOT CONNECTED / APP CODE UNCHANGED / NOT DEPLOYED
>
> 관련 요청: [Issue #178](https://github.com/sagesaint84/wealth/issues/178). 기존 홈 3탭 [Issue #176](https://github.com/sagesaint84/wealth/issues/176) / [Draft PR #177](https://github.com/sagesaint84/wealth/pull/177)는 모바일 성능 FAIL/HOLD로 독립 보존한다.
>
> 기준 소스: main@940a42053297059dcbafdc837458876269958086, APP_VERSION 2.1.3.

## 1. 목적과 엄격한 구분

목표는 국내 **주식시장**(KOSPI/KOSDAQ 기반)과 미국 **주식시장**의 공포·탐욕 수치를 근거와 함께 제공하는 것. 비트코인/암호화폐 지수와 혼동하지 않는다. 0점은 극도의 공포이지 값이 없거나 API 오류인 상태가 아니다.

- **미국**: CNN 게시자 지수를 합법적으로 읽을 수 있으면 해당 점수와 실제 출처/시각 표시. 그렇지 않으면 기존 CNN 공식 페이지 링크만 유지. 공개 설명을 대략 흉내 낸 자체 산출값은 CNN 게시자 수치로 표기하지 않는다.
- **한국**: KRX 공식 0~100 공포탐욕지수가 공개 OPEN API 목록에서 발견되지 않았다. 실제 데이터 사용 권한과 자체 산식·검증이 확보된다면 **Wealth 자체 산출 한국 시장심리지수**라고 표시. KRX 공식 발표 점수라고 표시하지 않는다.
- **기능 위치**: 홈 3탭을 네 번째 탭으로 확장하는 요청이 아니다. 향후 주요지수 화면에서 심리 카드의 배치 여부를 검토하되 PR #177은 수정하지 않는다.

## 2. 공개 자료로 확인된 사실과 미확인 사항

| 시장 | 공개 근거 | 확인됨 | 미확인 / 출고 차단 |
| --- | --- | --- | --- |
| 미국 | CNN Fear & Greed 인덱싱된 설명 | 0~100, 일곱 지표 동일 가중 설명; 모멘텀/강도/시장 폭/풋콜/정크본드/변동성/안전자산 | 공식 자동 수집 API, 제품 내 표시/재배포권, 신선도 SLA, 정확한 점수 정규화 방식 |
| 한국 | KRX OPEN API 서비스 목록 | KOSPI/KOSDAQ/KRX 일별 지수, 종목 거래, 파생/옵션 일별 데이터 API 확인 | 공식 공포탐욕 0~100 공급자 미확인, 자체 모델 가중치·정규화·결측 처리 검증 필요 |
| 한국 데이터 권리 | KRX OPEN API 약관 | API 이용 비상업적 목적, 일부 제3자 제공 제한, 서비스 표시 출처 조건, 승인된 키 필요 | 현재 앱 사용 목적과 공개/공유·파생 산출·캐시의 계약 적합성; 확인 전 자동 연결 금지 |
| 한국 변동성 | KRX 코스피200 변동성지수 안내 | 코스피200 옵션 기반 30일 기대변동성 지표가 있다 | 해당 수치를 공포탐욕 0~100 점수로 치환할 근거 없음 |

CNN의 일곱 지표: ① S&P500/125일선 시장 모멘텀 ② NYSE 52주 신고/저가 주가 강도 ③ McClellan 기반 시장 폭 ④ 풋/콜 옵션 ⑤ 정크본드 수요 ⑥ VIX 시장 변동성 ⑦ 주식/채권 안전자산 선호. 공개 설명은 각각 평균 대비 편차를 기준으로 동일 가중 합성한다고 하지만 내부 정규화 상세 계약이 확인되지 않았다.

주의: 미국 CNN 공식 페이지 자체는 검색 봇이 robots 정책으로 직접 열리지 않았다. 확인한 설명은 검색에 제공된 CNN 사이트의 인덱싱된 내용(일부 과거 캐시)이다. 정확한 현재 지수 값이나 내부 API 응답을 인증하지 않았다. 내부/비공식 endpoint, 우회 프록시, 무허가 scraping을 이용한 직접 연동은 구현하지 않는다.

KRX는 공식 API 목록에 'Fear & Greed 0~100' 전용 서비스를 나열하지 않았다. 이는 전체 금융시장에서 관련 제공자가 전혀 없다는 보편적 부정은 아니다. KRX 변동성지수(V-KOSPI 200)는 단독으로 0~100 공포탐욕 점수가 아니다.

## 3. 자료 접근·라이선스 사전 승인 게이트

US_PROVIDER_LICENSE_GATE:
- 게시자로부터 **문서화된 점수 API/정식 데이터 피드** 또는 사용권이 확인되어야 한다.
- 요청 엔드포인트, 허용 호출·캐싱·재표시·출처 의무·만료 조건을 기록한다.
- 유효한 근거 전까지 US의 score=null, status=not_connected, CNN 공식 페이지 링크 유지.

KRX_DATA_RIGHTS_GATE:
- 이용 목적(비상업/가족 내부 이용/외부 공유), 데이터 호출 자격, 합성 산출물의 표시·배포·영속 저장 가능 여부를 확인한다.
- 승인된 키는 서버 보안 저장소에서만 읽고 프런트엔드·로그·테스트 fixture에 기록 금지.
- 원자료라면 KRX 출처 표시와 자체 계산 표시를 분리하고 왜곡·무단 재배포 금지.
- KRX API 키를 가정하거나 공개 샘플 키로 운영 연결 금지.

기초 자료를 갖췄더라도 배포 권리가 확인되지 않은 상태에서는 **실수로 보이는 수치 생성이 아니라 not_connected로 안전하게 비연결** 처리한다.

## 4. 한국 자체 산식 설계 후보 (미결정)

점수화 후보만 지정하며, 숫자/가중치/기준선은 아직 승인되지 않았다.

| 구성 요소 후보 | 관찰치 예시 | 판단해야 할 세부 |
| --- | --- | --- |
| 추세/모멘텀 | KOSPI 및 KOSDAQ의 장기 이동평균 대비 편차 | 기간, KOSPI/KOSDAQ 가중, 상승 방향 |
| 시장 폭 | 상승/하락 종목 수 또는 거래량 기준 폭 | 휴장·거래정지·신규상장 처리 |
| 변동성 | VKOSPI 수준 또는 과거 대비 분포 | 높을수록 공포 방향, 자료 접근권 |
| 옵션 심리 | KOSPI200 옵션 P/C 비율 | 거래량/미결제약정, 만기월 변동, 결측 |
| 수급/위험선호 | 외국인·기관 순매수와 거래대금 | 자금 규모 정규화·시총 조정 |

구현에 앞서 다음을 명시적으로 결정한다: 구성 요소별 출처/권리, 거래일 정렬, 표준화 관찰 창과 결측 허용률, 분모 0 처리, 역방향 부호, 가중치, 0..100 변환식, 표준 5단계의 수치 경계, 업데이트 시각과 영업일 기준, 모델 버전, 과거 자료를 사용한 표본외 검증 및 급락일 민감도. 백테스트 성공 전 실제 점수는 null을 유지한다.

## 5. 향후 API 계약 제안 (확정 전)

실제 값이 허용될 때만 아래와 유사한 시장별 구조를 도입한다.

~~~json
{
  "market": "KR",
  "index_name": "Wealth 한국 시장심리지수",
  "score": null,
  "band": null,
  "provider": "UNVERIFIED",
  "method": null,
  "method_version": null,
  "source_url": null,
  "observed_at": null,
  "retrieved_at": null,
  "status": "not_connected",
  "reason": "데이터 이용권 및 자체 산식 미검증",
  "components": null
}
~~~

- market 구분은 KR/US. method는 publisher_index / wealth_derived / null 중 하나. 출처 식별자·합성 모델 버전이 없으면 공식 점수로 표기 금지.
- status는 ok / stale / source_error / not_connected. score는 null 또는 유한한 0..100 수치; bool, NaN, Infinity, 문자·시간 오류는 거절한다.
- ok에는 출처·관찰 시각(timezone 포함)·수집 시각이 필요하다. 관측일이 다른 시장 간 동시 비교는 금지.
- 데이터 누락과 응답 실패는 0점으로 채우지 않으며, 과거 점수는 기준 시각과 stale로 구분해서 표시한다.
- 주말/휴장·시차/늦은 응답과 복수 요청을 처리. read-only 요청이어야 하고 금융·계좌·비밀키 파일을 변경하지 않는다.
- 사업자 지수의 등급 구간은 사업자 설명과 일치시켜야 하고, Wealth 자체 점수의 구간은 산식 확정 후 결정한다. CNN 등급 경계를 임의로 단정하지 않는다.
- 캐시는 기존 MarketReadCache의 격리·singleflight·유한 TTL·실패 backoff를 참고하되 게시자 이용조건에 맞춰 결정한다.
- **초기 포트폴리오 화면에 추가 외부 API 요청, 신규 JS 번들/차트 렌더를 넣지 않는다.** 시장 화면 진입에서만 읽는 원칙을 우선 검토한다(현행 home 3-tab PR HOLD와 충돌하지 않게 별도 검증).

## 6. 단계별 승인 및 테스트 게이트

Phase 0 (현재): 근거 문서와 Issue #178만. 앱 변경/실제 점수/배포 없음.
Phase 1: US 제공자 라이선스·공식 경로, KR 원천자료 이용조건·산식·검증 창을 문서로 입증. 미확인 공급원은 UI 링크만.
Phase 2: 별도 feature branch에서 합성 fixture로 source adapter/score validator를 작성. source_error/stale/null/timezone/범위·동시요청·로그/저장소 무유출·화면 비활성 요청 0을 테스트.
Phase 3: 허용된 시장에 한해 UI 연동. 비연결 시장은 명시적 정보 부재 표시, 실제 없는 점수/허위 선호 등급 금지. 320/360/390/768/1280px Chromium과 독립 성능 비교.
Phase 4: 관련 CI/회귀 성공과 실제 사용권 확인 후 **사용자 승인 하에** merge/release/deploy. PR #177의 모바일 HOLD를 우회하여 해당 기능을 배포하지 않는다.

Gates:
- SOURCE_RESEARCH=RECORDED
- US_SCORE_PROVIDER=UNVERIFIED
- KR_OFFICIAL_SCORE=NOT_FOUND_IN_REVIEWED_KRX_CATALOG
- KR_DERIVED_METHOD=UNDEFINED
- DATA_RIGHTS=UNVERIFIED
- SCORE_IMPLEMENTATION=NOT_STARTED
- HOME_TABS_PR177=HOLD_UNCHANGED
- RELEASE_DEPLOY=NOT_AUTHORIZED

## 7. 검증 출처

1. CNN 공개 소개: https://www.cnn.com/markets/fear-and-greed (직접 자동 접근 제한)
2. CNN 인덱싱된 방법론: https://www-stage-fastly.stellar.cnn.com/markets/fear-and-greed (검색 결과 시점의 기록, 자동 데이터 API 아님)
3. KRX OPEN API 서비스 목록: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
4. KOSPI 지수 일별 API 필드: https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN
5. KRX OPEN API 국문 이용약관: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp
6. KRX Data Marketplace: https://data.krx.co.kr/
7. KRX 코스피200 변동성지수선물 설명: https://www.krx.co.kr/contents/OPN/01/01040301/OPN01040301T1.jsp

기록 일자 2026-10-25. 조사 결과는 당시 확인한 공개 자료에 한정한다.
