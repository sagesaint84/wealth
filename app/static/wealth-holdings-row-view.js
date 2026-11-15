/* Shared holding rows only: no data selection, aggregation, DOM access or event registration. */
(() => {
  'use strict';

  function create({ html, number, money, signClass }) {
    function renderAccountDetail(detail, variant = 'general') {
      const quantityDigits = variant === 'tax' ? 0 : 4;
      return `
      <span class="holding-account-detail">
        ${html(detail.broker)} ${html(detail.accountName)}${html(detail.ownerLabel || '')} ${number(detail.quantity, quantityDigits)}주
        <button class="mini-edit-button edit-button" data-id="${detail.id}" title="수정" type="button">✎</button>
        <button class="mini-edit-button delete-button" data-id="${detail.id}" title="삭제" type="button">×</button>
      </span>
    `;
    }

    function renderRow(item, { accounts, variant = 'general' }) {
      const isTax = variant === 'tax';
      const quantityDigits = isTax ? 0 : 4;
      const alignment = isTax ? ' style="text-align:left;"' : '';
      const formatAmount = isTax ? value => `₩${number(value, 0)}` : money;
      const dayRate = Number(item.day_change_rate || 0);
    return `
      <tr data-code="${html(item.code)}">
        <td class="holding-name-cell"${alignment}>
          <strong class="holding-name-link" data-code="${html(item.code)}" data-name="${html(item.name)}" data-price="${item.current_price}" data-currency="${item.currency}">
            ${html(item.name)}
          </strong>
          <small>${html(item.code)} · ${html(item.market || item.currency || (isTax ? 'KRW' : item.currency))}</small>
        </td>
        <td${alignment}>
          <span class="sector-badge">${html(item.sector || '기타')}</span>
        </td>
        <td class="holding-accounts"${alignment}>${accounts}</td>
        <td>${number(item.quantity, quantityDigits)}</td>
        <td><strong>${formatAmount(item.market_value_krw)}</strong></td>
        <td class="${signClass(item.profit_krw)}">${item.profit_krw >= 0 ? "+" : ""}${formatAmount(item.profit_krw)}</td>
        <td class="${signClass(item.return_rate)}">${item.return_rate >= 0 ? "+" : ""}${number(item.return_rate, 2)}%</td>
        <td class="${signClass(dayRate)}">${dayRate >= 0 ? "+" : ""}${number(dayRate, 2)}%</td>
        <td style="text-align:center;">
          <button class="stock-chart-btn" data-code="${html(item.code)}" data-name="${html(item.name)}" data-price="${item.current_price}" data-currency="${item.currency}" title="인터랙티브 차트" type="button">
            📊
          </button>
        </td>
      </tr>
    `;
    }

    return Object.freeze({ renderRow, renderAccountDetail });
  }

  window.WealthHoldingsRowView = Object.freeze({ create });
})();
