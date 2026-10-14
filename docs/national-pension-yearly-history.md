# 국민연금 연도별 실제 납부 이력

기존 v2.0.1 납부 이력 구현은 PR #143 기준 HEAD acfe0a7에서 사용자 확인 전체
pytest 3,596 passed / 5 skipped / 0 failed, subtests 798 passed, Chrome UI 30 passed
및 AMD64/ARM64 CI 성공을 기록했다. 당시 [후속 상세 분석](national-pension-analysis.md)은
별도 미커밋 구현·검증 전 상태였다. 현재 v2.0.2 PR #144에서는 사용자 확인 Windows
전체 pytest 3,699 passed / 5 skipped / 0 failed / 5 warnings, 798 subtests passed,
Python·JS 문법 PASS와 Actions run 38493482329 attempt #8 native amd64/arm64 CI 성공을
기록한다. PR은 2026-10-14 기준 Draft/main 반영 전이며 v2.0.2 운영 검증·배포는 미실행이다.
종합 자산 탭의 표시 이름은 연금·보험이다. category key와 count는 유지한다.

국민연금 카드의 연도별 실제 납부 이력을 펼쳐 납부 이력 편집을 연다.
국민연금공단에서 확인한 연도와 실제 연간 보험료를 추가·수정·삭제하고
명시적으로 저장한다. 최초 연도와 당해연도도 확인한 부분 납부액 그대로 입력한다.
빈 연도를 과거 납부로 추정하거나 월 보험료로 소급 생성하지 않는다.

portfolio.json의 해당 insurance_accounts 항목 내부 yearly_contributions를
재사용한다. 각 항목은 year(4자리 문자열)와 deposit(실제 납부액)이다.
국민연금 제도 시작 연도인 1988년부터 당해연도까지 허용하며 중복 연도,
누락 금액, 음수, NaN/Infinity는 거부한다. 명시적 0원은 납부 없음이며,
기록이 없는 연도는 미확인이다. 미확인 안내 행은 화면에만 존재하고 저장하지 않는다.

전용 PUT /api/insurance-accounts/{id}/yearly-contributions는 현재 로그인한
사용자의 국민연금 상품만 변경한다. portfolio.json의 canonical RMW 잠금
안에서 이력만 교체한다. expected_history가 이전 저장값과 다르면 409로
거부하여 다른 편집을 덮어쓰지 않는다. 일반 상품 수정에서 이력 필드를
생략하면 기존 이력을 보존하고, 명시적으로 보내면 국민연금에만 검증한다.

누적납입액과 이력 합계가 다르면 차이를 안내한다. 어느 쪽도 자동 덮어쓰지
않으며 total_paid_amount, 월 연금액, 예상 수령액, 환산액, owner와 날짜는
이력 전용 저장으로 변경하지 않는다. maturity_date는 연금 개시 예정일일
수 있으며 보험료 납부 종료일로 해석하거나 미래 이력을 생성하지 않는다.

노란우산 기록·소득공제 한도·절세 계산은 그대로다. 국민연금 이력에는
is_deductible, 절세율 또는 노란우산 세금 계산을 적용하지 않는다.
기준 HEAD의 이력 기능에는 IRR·미래 납입 계산기가 없었다. 후속 분석은
별도 선택 메타데이터와 표시용 현금흐름으로 제공하며 기존 실제 납부 이력·
금융 금액·Toss 2행 UI를 유지한다.

기존 기준 HEAD 검증 기록과 현재 v2.0.2 검증 결과는 위에서 구분한다.
합성 검증에 실제 데이터·인증정보·운영 서버를 사용하지 않았다.
