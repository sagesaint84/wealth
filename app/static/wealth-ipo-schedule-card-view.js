(() => {
  'use strict';

  const SCORE_CORE_LABELS = {
    institutional_competition_ratio: '기관경쟁률',
    lockup_commitment_ratio: '의무보유확약률',
    tradable_share_ratio: '유통가능주식비율',
    pricing_discipline: '공모가 결정정보',
  };
  function scoreDiagnosticText(score) {
    if (!score || typeof score !== 'object') return '점수 데이터가 아직 생성되지 않았습니다.';
    if (score.status === 'NOT_APPLICABLE') return '';
    if (typeof score.score === 'number' && Number.isFinite(score.score)) return '';
    const isCalculating = score.is_calculating === true || score.score === null || score.score === undefined;
    if (!isCalculating) return '';

    const parts = [];
    const coverage = Number(score.coverage);
    if (Number.isFinite(coverage)) parts.push(`데이터 ${coverage}%`);
    const missing = Array.isArray(score.core_missing) ? score.core_missing : [];
    if (missing.length > 0) {
      const labels = missing.map(key => SCORE_CORE_LABELS[key] || String(key));
      parts.push(`부족: ${labels.join(', ')}`);
    } else if (Number.isFinite(coverage) && coverage < 75) {
      parts.push('정식 점수 기준 75% 미만');
    }
    return parts.join(' · ') || '점수 입력 데이터를 확인 중입니다.';
  }

  function trustedMetalogosUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
      const url = new URL(raw);
      const host = url.hostname.toLowerCase();
      if (url.protocol !== 'https:') return '';
      if (host !== 'metalogos.ai' && host !== 'www.metalogos.ai') return '';
      if (!url.pathname.startsWith('/160ipo/stock/')) return '';
      return url.href;
    } catch (_err) {
      return '';
    }
  }

  function compactReferenceNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '';
    return Number.isInteger(number) ? number.toLocaleString('ko-KR') : String(number);
  }

  function renderMetalogosReference(ipo, escapeHtml) {
    const reference = ipo?.sources?.metalogos160;
    if (!reference || typeof reference !== 'object') return '';
    const sourceUrl = trustedMetalogosUrl(reference.url);
    const value = compactReferenceNumber(reference.attractiveness_score);
    const metric = value ? `매력지수 ${value}` : '';
    if (!sourceUrl && !metric) return '';
    const link = sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">160 원문</a>` : '';
    return `<span class="ipo-metalogos-reference" title="Metalogos 160 공개자료의 참고값입니다. Wealth IPO Score 산정에는 사용하지 않습니다.">${link}${escapeHtml(`${link && metric ? ' · ' : ''}${metric}`)}</span>`;
  }

  window.WealthIpoScheduleCardView = Object.freeze({ scoreDiagnosticText, renderMetalogosReference });
})();
