(() => {
  'use strict';

  function selectOwnerRecords(records, owner) {
    if (owner === '모두') {
      const allOwnerRecords = records.filter(record => (record.owner || '모두') === '모두');
      return allOwnerRecords.length > 0 ? allOwnerRecords : records;
    }
    return records.filter(record => (record.owner || '모두') === owner);
  }

  function filterRecordsByPeriod(records, period) {
    if (!records || !records.length || period === 'ALL') return records || [];
    const sorted = [...records].sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));

    if (period === '1D') {
      // 일간: 전날과 당일 2일만 비교
      return sorted.slice(-2);
    }
    if (period === '1W') {
      // 주간: 5일간 비교
      return sorted.slice(-5);
    }
    if (period === '1M') {
      // 월간: 1달간 비교 (최근 30일)
      const now = new Date();
      const cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
      const mList = sorted.filter(r => r.date && r.date >= cutoff);
      return mList.length >= 2 ? mList : sorted.slice(-30);
    }
    if (period === '1Y') {
      // 연간: 1년간 비교 (최근 365일)
      const now = new Date();
      const cutoff = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
      const yList = sorted.filter(r => r.date && r.date >= cutoff);
      return yList.length >= 2 ? yList : sorted.slice(-365);
    }
    return sorted;
  }

  function buildPreviousRecordMap(records) {
    const previousByRecord = new Map();
    const latestByOwner = new Map();
    records.forEach(record => {
      const owner = record.owner || '모두';
      previousByRecord.set(record, latestByOwner.get(owner) || null);
      latestByOwner.set(owner, record);
    });
    return previousByRecord;
  }

  window.WealthStockRecordsModel = Object.freeze({ selectOwnerRecords, filterRecordsByPeriod, buildPreviousRecordMap });
})();
