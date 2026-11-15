/* Market cards View: owns rendered market data and its sentiment expiry timer only. */
(() => {
  'use strict';

  function create({ $, html, number, getCurrentMarketPeriod, getCurrentMarketAllSub,
                    marketCardKey, hiddenMarketCards, marketCardSettings, document }) {
let marketOverviewData = null;
let marketFearGreedExpiryTimer = null;

function sparkline(points, change) {
  if (!points || points.length < 2) {
    if (points && points.length === 1) points = [points[0], points[0]];
    else return "<span class=\"spark-empty\">—</span>";
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || (min * 0.01) || 1;
  const h = 42;
  const w = 110;
  const pad = 4;

  const coords = points.map((point, index) => {
    const x = (index / (points.length - 1)) * (w - pad * 2) + pad;
    const y = (h - pad) - ((point - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polylineStr = coords.join(" ");
  const lastCoord = coords[coords.length - 1].split(",");
  const lastX = lastCoord[0];
  const lastY = lastCoord[1];

  const isUp = Number(change) > 0;
  const isDown = Number(change) < 0;
  const color = isUp ? "#ff5c77" : (isDown ? "#4f9dff" : "#98a6c8");

  return `
    <svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="${polylineStr}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      <circle cx="${lastX}" cy="${lastY}" r="3" fill="${color}" />
    </svg>
  `;
}

function renderMarketFearGreed(item) {
  clearTimeout(marketFearGreedExpiryTimer);
  marketFearGreedExpiryTimer = null;
  if (!item) return '';
  const labels = {'Extreme Fear':'극도의 공포','Fear':'공포','Neutral':'중립','Greed':'탐욕','Extreme Greed':'극도의 탐욕'};
  const until = typeof item.valid_until === 'string' ? Date.parse(item.valid_until) : NaN;
  const updated = typeof item.relay_updated_at === 'string' ? Date.parse(item.relay_updated_at) : NaN;
  const day = typeof item.observed_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.observed_date) ? item.observed_date : null;
  const good = item.status === 'ok' && typeof item.score === 'number' && Number.isFinite(item.score)
    && item.score >= 0 && item.score <= 100 && Object.hasOwn(labels, item.rating)
    && day && Number.isFinite(updated) && Number.isFinite(until) && until > Date.now();
  let value = '출처 오류 · 점수 조회 불가';
  if (good) {
    value = `<strong class="market-sentiment-score market-price" data-cnn-score>${html(number(item.score, 2))} (${html(labels[item.rating])})</strong>`;
    marketFearGreedExpiryTimer = setTimeout(() => {
      marketFearGreedExpiryTimer = null;
      const node = document.getElementById('marketFearGreed');
      if (node && marketOverviewData?.fear_greed === item) node.outerHTML = renderMarketFearGreed(item);
    }, Math.min(2147483647, Math.max(1, until - Date.now() + 1)));
  } else if (item.status === 'stale' || (item.status === 'ok' && Number.isFinite(until) && until <= Date.now())) {
    value = '갱신 지연 · 오래된 점수는 표시하지 않습니다';
  } else if (item.status === 'not_connected') {
    value = '출처 조회 불가 · 점수 미연동';
  }
  const stamp = Number.isFinite(updated)
    ? new Date(updated).toLocaleString('ko-KR', {timeZone:'Asia/Seoul', hour12:false}) : null;
  return `<article id="marketFearGreed" class="market-card toss-market-card market-sentiment" aria-label="미국 CNN 공포·탐욕">
    <strong class="market-title">공포탐욕지수</strong><div role="status">${value}</div><details><summary>출처 및 기준 시각</summary><span class="market-sentiment-time">CNN 지수 · 비공식 데이터 중계</span>
    ${day ? `<span class="market-sentiment-time">중계 기준일 ${html(day)}</span>` : ''}
    ${stamp ? `<span class="market-sentiment-time">중계 파일 갱신 ${html(stamp)} KST</span>` : ''}
    <span>실시간 보장 없음 · <a href="https://www.cnn.com/markets/fear-and-greed" target="_blank" rel="noopener noreferrer">CNN 공식 페이지</a>
    · <a href="https://github.com/chirag127/fear-greed-index-api" target="_blank" rel="noopener noreferrer">중계 GitHub 프로젝트</a></span></details></article>`;
}

function renderMarkets(result) {
  if (result) marketOverviewData = result;
  if (!marketOverviewData) return;

  const mkts = marketOverviewData.markets || [];
  const fx = marketOverviewData.exchange_rate || {};
  let period = getCurrentMarketPeriod() || '1D';
  if (period === 'ALL') {
    period = getCurrentMarketAllSub() || '3Y';
  }

  const allCards = [
    ...mkts.map(m => {
      const pStat = (m.periods && (m.periods[period] || m.periods['ALL'])) || {};
      const change = pStat.change != null ? pStat.change : (m.change != null ? m.change : m.change_price);
      const changeRate = pStat.change_rate != null ? pStat.change_rate : m.change_rate;
      const series = (pStat.series && pStat.series.length) ? pStat.series : (m.series || [m.price || 0]);
      let lbl = m.label || m.name;
      if (lbl === "S&P 500") lbl = "S&P";
      if (lbl === "달러 환율") lbl = "달러";
      return {
        symbol: m.symbol,
        label: lbl,
        price: m.price != null ? m.price : m.current_price,
        currency: m.currency || 'KRW',
        change: change,
        change_rate: changeRate,
        series: series,
      };
    }),
    (() => {
      const fxPStat = (fx.periods && (fx.periods[period] || fx.periods['ALL'])) || {};
      const fxChange = fxPStat.change != null ? fxPStat.change : (fx.change != null ? fx.change : fx.change_price);
      const fxChangeRate = fxPStat.change_rate != null ? fxPStat.change_rate : fx.change_rate;
      const fxSeries = (fxPStat.series && fxPStat.series.length) ? fxPStat.series : (fx.series || [fx.rate || 1385]);
      return {
        symbol: "USD/KRW",
        label: "달러",
        price: fx.rate,
        currency: "KRW",
        change: fxChange,
        change_rate: fxChangeRate,
        series: fxSeries,
      };
    })(),
    ...(marketOverviewData.rates || [])
  ];

  // 순서: 코스피 -> 코스닥 -> 달러 -> S&P -> 나스닥 -> 반도체
  const ORDER = ["코스피", "코스닥", "달러", "S&P", "나스닥", "반도체"];
  const rows = ORDER.map(name => allCards.find(c => c.label === name)).filter(Boolean);
  allCards.forEach(c => {
    if (!rows.includes(c)) rows.push(c);
  });

  const grid = $("#marketGrid");
  if (!grid) return;

  const hidden=hiddenMarketCards();
  marketCardSettings([...rows.map(item=>({key:marketCardKey(item),label:item.kind==='yield'?'금리':item.label})),{key:'cnn-fng',label:'공포탐욕지수'}]);
  clearTimeout(marketFearGreedExpiryTimer);marketFearGreedExpiryTimer=null;
  grid.innerHTML = rows.filter(item=>!hidden.has(marketCardKey(item))).map((item) => {
    if (item.kind === 'yield') {
      const change = item.value == null || item.change_bp == null ? '—' : `${item.change_bp > 0 ? '+' : ''}${number(item.change_bp, 1)}bp`;
      const tone = item.change_bp > 0 ? 'up' : item.change_bp < 0 ? 'down' : '';
      return `<article class="market-card toss-market-card" data-market-symbol="${html(item.symbol)}">
        <div class="market-chart-col">${sparkline(item.value == null ? [] : item.series, item.change_bp)}</div>
        <div class="market-info-col"><strong class="market-title">금리</strong>
          <strong class="market-price ${tone}">${item.value == null ? '조회 불가' : number(item.value, 3) + '%'}</strong>
          <span class="market-change-point ${tone}">${change}</span>
        </div></article>`;
    }
    const isFx = item.symbol === "USD/KRW";
    const priceText = isFx ? `${number(item.price, 1)}원` : number(item.price, 2);

    const isUp = Number(item.change_rate) > 0;
    const isDown = Number(item.change_rate) < 0;
    const sign = isUp ? "+" : "";
    const colorClass = isUp ? "up" : (isDown ? "down" : "");

    let changePointText = "";
    let changeRateText = "";
    if (item.change_rate != null) {
      changePointText = item.change != null ? `${sign}${number(item.change, 2)}` : "—";
      changeRateText = `${sign}${number(item.change_rate, 2)}%`;
    } else {
      changePointText = "—";
      changeRateText = "—";
    }

    const chartHtml = sparkline(item.series, item.change_rate);

    return `
      <article class="market-card toss-market-card">
        <div class="market-chart-col">
          ${chartHtml}
        </div>
        <div class="market-info-col">
          <strong class="market-title">${html(item.label)}</strong>
          <strong class="market-price ${colorClass}">${priceText}</strong>
          <span class="market-change-point ${colorClass}">${changePointText}</span>
          <span class="market-change-rate ${colorClass}">${changeRateText}</span>
        </div>
      </article>
    `;
  }).join("") + (hidden.has('cnn-fng') ? '' : renderMarketFearGreed(marketOverviewData.fear_greed));
  if(!grid.childElementCount){
    const empty=document.createElement('p'),button=document.createElement('button');empty.textContent='표시할 지수를 선택하세요';button.type='button';button.className='button secondary';button.textContent='표시 설정';button.onclick=()=>document.getElementById('marketCardSettings').click();empty.append(button);grid.append(empty);
  }
}

    return Object.freeze({ renderMarkets, renderMarketFearGreed, sparkline,
      hasData: () => !!marketOverviewData,
      getData: () => marketOverviewData });
  }

  window.WealthMarketView = Object.freeze({ create });
})();
