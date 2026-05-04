/**
 * Binance geçmiş OHLCV — public REST /api/v3/klines
 *
 * Not: Canlı backtest akışı node-backend içinde
 * `node-backend/src/services/binanceBacktestService.ts` üzerinden yürür.
 * Bu dosya aynı sözleşmeyi dokümante eder ve bağımsız script/test için kullanılabilir.
 */

const axios = require('axios');

const BINANCE = 'https://api.binance.com';

const DEFAULT_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  Accept: 'application/json',
};

/**
 * @param {string} symbol Örn. BTCUSDT
 * @param {string} interval Örn. 1d
 * @param {number} startMs
 * @param {number} endMs
 * @returns {Promise<any[]>} Ham klines dizisi
 */
async function fetchKlinesPage(symbol, interval, startMs, endMs, limit = 1000) {
  const { data } = await axios.get(`${BINANCE}/api/v3/klines`, {
    params: { symbol, interval, startTime: startMs, endTime: endMs, limit },
    headers: DEFAULT_HEADERS,
    timeout: 30000,
    validateStatus: (s) => s === 200,
  });
  return data;
}

/**
 * Tüm aralığı sayfalayarak çeker (max 1000 mum / istek).
 */
async function fetchAllKlines(symbol, interval, startMs, endMs) {
  const out = [];
  let cursor = startMs;
  while (cursor <= endMs) {
    const batch = await fetchKlinesPage(symbol, interval, cursor, endMs, 1000);
    if (!batch.length) break;
    out.push(...batch);
    const last = batch[batch.length - 1][0];
    cursor = last + 1;
    if (batch.length < 1000) break;
  }
  return out;
}

module.exports = {
  BINANCE,
  fetchKlinesPage,
  fetchAllKlines,
};
