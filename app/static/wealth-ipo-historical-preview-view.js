(() => {
  "use strict";

  function historicalIssueLabel(reason) {
    const labels = {
      COMPANY_NAME_MISSING: '회사명 누락',
      STOCK_CODE_INVALID: '종목코드 오류',
      ACTUAL_LISTING_DATE_INVALID: '상장일 형식 오류',
      ACTUAL_LISTING_DATE_IN_FUTURE: '미래 실제 상장일',
      FINAL_OFFER_PRICE_INVALID: '확정 공모가 오류',
      NOT_NEW_LISTING: '신규상장이 아닌 행',
      DUPLICATE_STOCK_CODE: '기존 데이터 종목코드 중복',
      DUPLICATE_COMPANY_NAME_CONFLICT: '파일 내 회사명 충돌',
      DUPLICATE_LISTING_DATE_CONFLICT: '파일 내 상장일 충돌',
      DUPLICATE_OFFER_PRICE_CONFLICT: '파일 내 공모가 충돌',
      DUPLICATE_LISTING_TRACK_CONFLICT: '파일 내 상장유형 충돌',
      DUPLICATE_MARKET_CONFLICT: '파일 내 시장구분 충돌',
      DUPLICATE_OFFERING_AMOUNT_CONFLICT: '파일 내 공모금액 충돌',
      DUPLICATE_OFFER_SHARES_CONFLICT: '파일 내 공모주식수 충돌',
      COMPANY_NAME_CONFLICT: '기존 회사명과 충돌',
      ACTUAL_LISTING_DATE_CONFLICT: '기존 상장일과 충돌',
      FINAL_OFFER_PRICE_CONFLICT: '기존 공모가와 충돌',
    };
    return labels[reason] || reason || '검토 필요';
  }

  function renderMessage(message) {
    const preview = document.getElementById('ipoHistoricalImportPreview');
    if (!preview) return;
    preview.replaceChildren();
    const paragraph = document.createElement('p');
    paragraph.textContent = String(message || '');
    preview.appendChild(paragraph);
  }

  function appendIssues(preview, issues, heading, showRowNumbers = false) {
    if (!Array.isArray(issues) || !issues.length) return false;

    const title = document.createElement('strong');
    title.textContent = heading;
    preview.appendChild(title);

    const list = document.createElement('ul');
    list.className = 'ipo-historical-preview-issues';
    issues.forEach(issue => {
      const row = document.createElement('li');
      const identity = [issue?.company_name, issue?.stock_code].filter(Boolean).join(' · ');
      row.textContent =
        `${showRowNumbers && issue?.row_number ? `${issue.row_number}행 · ` : ''}` +
        `${identity ? `${identity} · ` : ''}${historicalIssueLabel(issue?.reason)}`;
      list.appendChild(row);
    });
    preview.appendChild(list);
    return true;
  }

  function render(payload) {
    const preview = document.getElementById('ipoHistoricalImportPreview');
    if (!preview) return;
    preview.replaceChildren();

    if (payload?.source === 'KRX_HISTORICAL_ONLINE') {
      const s = payload?.summary || {};
      const summary = document.createElement('p');
      summary.className = 'ipo-historical-preview-summary';
      summary.textContent =
        `KRX 온라인 ${payload?.from_year || ''}~${payload?.to_year || ''} · 조회 ${s.fetched || 0}` +
        ` / 신규 ${s.new || 0} / 정정 ${s.updated || 0} / 동일 ${s.unchanged || 0}` +
        ` / 검토 필요 ${s.review_required || 0} / 무효 ${s.invalid || 0}`;
      preview.appendChild(summary);

      const changes = Array.isArray(payload?.changes) ? payload.changes : [];
      if (changes.length > 0) {
        const title = document.createElement('strong');
        title.textContent = '반영 예정 변경';
        preview.appendChild(title);
        const fieldLabels = {
          market: '상장시장', actual_listing_date: '실제 상장일',
          final_offer_price: '확정 공모가', lead_managers: '주관사', listing_track: '상장유형'
        };
        const valueText = (value) => Array.isArray(value) ? value.join(', ') : (value ?? '—');
        const list = document.createElement('ul');
        list.className = 'ipo-historical-preview-issues';
        changes.forEach((item) => {
          const row = document.createElement('li');
          const identity = [item?.company_name, item?.stock_code].filter(Boolean).join(' · ');
          if (item?.classification === 'NEW') {
            row.textContent = `${identity} · 신규 과거 공모주 추가`;
          } else {
            const diffs = (item?.changes || []).map(change =>
              `${fieldLabels[change.field] || change.field}: ${valueText(change.before)} → ${valueText(change.after)}`
            );
            row.textContent = `${identity} · ${diffs.join(' / ')}`;
          }
          list.appendChild(row);
        });
        preview.appendChild(list);
      }
      if (payload?.changes_truncated) {
        const more = document.createElement('p');
        more.className = 'muted';
        more.textContent = `외 ${payload.changes_truncated}건의 반영 예정 항목이 있습니다.`;
        preview.appendChild(more);
      }
      appendIssues(preview, payload?.issues, '자동 반영하지 않는 검토 항목');
      return;
    }

    const s = payload?.summary || {};
    const sourceLabel = payload?.source === 'KRX_NEW_LISTINGS_EXPORT'
      ? 'KRX 신규상장종목 현황'
      : 'KIND 신규상장기업현황';

    const summary = document.createElement('p');
    summary.className = 'ipo-historical-preview-summary';
    summary.textContent =
      `${sourceLabel} · 전체 ${s.total_rows || 0}행 / 정상 ${s.valid_rows || 0}` +
      ` / 신규 ${s.new || 0} / 기존 존재 ${s.already_present || 0}` +
      ` / 보완 가능 ${s.enrichable || 0} / 검토 필요 ${s.review_required || 0}` +
      ` / 충돌 ${s.conflict || 0} / 무효 ${s.invalid || 0}` +
      `${s.duplicate_rows ? ` / 중복 제거 ${s.duplicate_rows}` : ''}`;
    preview.appendChild(summary);

    if (appendIssues(preview, payload?.issues, '검토 항목', true)) {
      if (payload?.issues_truncated) {
        const more = document.createElement('p');
        more.className = 'muted';
        more.textContent = `외 ${payload.issues_truncated}건의 검토 항목이 있습니다.`;
        preview.appendChild(more);
      }
    }
  }

  window.WealthIpoHistoricalPreviewView = Object.freeze({ render, renderMessage });
})();
