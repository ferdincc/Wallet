/**
 * Backtest engine: walk-forward validation, metrics (MAPE, RMSE, direction accuracy),
 * persist results to model_predictions.
 *
 * Usage: runBacktest(prisma, { symbol, modelName, startDate, endDate, windowDays }, options?)
 * Options: { pythonBackendUrl?, getModelPrediction?(modelName, data) }
 */

const { runArimaModel } = require('./models/arimaWrapper');
const path = require('path');

const DEFAULT_WINDOW_DAYS = 30;
const SUPPORTED_MODELS = ['prophet', 'lgbm', 'arima', 'ensemble'];

/**
 * Aggregate raw price_data rows to one row per calendar day (last close, etc.).
 * @param {Array<{ timestamp: Date, open: number, high: number, low: number, close: number, volume: number }>} rows
 * @returns {Array<{ date: string, timestamp: Date, open: number, high: number, low: number, close: number, volume: number }>}
 */
function aggregateToDaily(rows) {
  const byDate = new Map(); // dateKey -> { date, timestamp, open, high, low, close, volume }
  for (const r of rows) {
    const d = r.timestamp instanceof Date ? r.timestamp : new Date(r.timestamp);
    const key = d.toISOString().slice(0, 10);
    const existing = byDate.get(key);
    if (!existing) {
      byDate.set(key, {
        date: key,
        timestamp: d,
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
        volume: r.volume,
      });
    } else {
      existing.high = Math.max(existing.high, r.high);
      existing.low = Math.min(existing.low, r.low);
      existing.close = r.close;
      existing.volume += r.volume;
    }
  }
  const sorted = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  return sorted;
}

/**
 * Get one-step-ahead prediction from a model.
 * @param {string} modelName - 'prophet' | 'lgbm' | 'arima'
 * @param {Array<{ date: string, timestamp: Date, open: number, high: number, low: number, close: number, volume: number }>} dailyData
 * @param {{ pythonBackendUrl?: string, getModelPrediction?: (modelName: string, data: any) => Promise<{ predicted_price?: number | null }> }} options
 * @returns {Promise<{ predicted_price: number | null, error?: string }>}
 */
async function getModelPrediction(modelName, dailyData, options = {}) {
  const series = dailyData.map((r) => ({
    timestamp: r.timestamp instanceof Date ? r.timestamp.toISOString() : r.timestamp,
    close: r.close,
  }));

  if (options.getModelPrediction) {
    const out = await options.getModelPrediction(modelName, series, dailyData);
    return { predicted_price: out.predicted_price != null ? out.predicted_price : null, error: out.error };
  }

  if (modelName === 'arima') {
    const out = await runArimaModel(series);
    return {
      predicted_price: out.predicted_price != null ? out.predicted_price : null,
      error: out.error,
    };
  }

  if (modelName === 'prophet' || modelName === 'lgbm') {
    const url = options.pythonBackendUrl;
    if (url) {
      try {
        // eslint-disable-next-line global-require
        const axios = require('axios');
        const ohlcv = dailyData.map((r) => [
          r.timestamp instanceof Date ? r.timestamp.getTime() : new Date(r.timestamp).getTime(),
          r.open,
          r.high,
          r.low,
          r.close,
          r.volume,
        ]);
        const res = await axios.post(`${url.replace(/\/$/, '')}/api/v1/backtest/predict`, {
          model: modelName,
          ohlcv,
          periods: 1,
        }, { timeout: 60000 });
        const p = res.data?.predicted_price ?? res.data?.predictions?.[0]?.price;
        return { predicted_price: typeof p === 'number' ? p : null };
      } catch (e) {
        return { predicted_price: null, error: e.message || String(e) };
      }
    }
    // Fallback: use last close so engine still runs
    const lastClose = dailyData.length ? dailyData[dailyData.length - 1].close : null;
    return { predicted_price: lastClose, error: 'pythonBackendUrl not set; used last close' };
  }

  return { predicted_price: null, error: `Unknown model: ${modelName}` };
}

/**
 * Run walk-forward backtest for one model.
 * @param {import('@prisma/client').PrismaClient} prisma
 * @param {{ symbol: string, modelName: string, startDate: string, endDate: string, windowDays?: number }} params
 * @param {{ pythonBackendUrl?: string, getModelPrediction?: (modelName: string, data: any, dailyData?: any) => Promise<{ predicted_price?: number | null }> }} options
 * @returns {Promise<{ model: string, avgMAPE: number, avgRMSE: number, directionAccuracy: number, totalPredictions: number, results: Array<any>, error?: string }>}
 */
async function runBacktest(prisma, params, options = {}) {
  const { symbol, modelName, startDate, endDate, windowDays = DEFAULT_WINDOW_DAYS } = params;

  if (!SUPPORTED_MODELS.includes(modelName)) {
    return {
      model: modelName,
      avgMAPE: 0,
      avgRMSE: 0,
      directionAccuracy: 0,
      totalPredictions: 0,
      results: [],
      error: `Unsupported model: ${modelName}. Use one of: ${SUPPORTED_MODELS.join(', ')}`,
    };
  }

  const start = new Date(startDate);
  const end = new Date(endDate);
  if (isNaN(start.getTime()) || isNaN(end.getTime()) || start >= end) {
    return {
      model: modelName,
      avgMAPE: 0,
      avgRMSE: 0,
      directionAccuracy: 0,
      totalPredictions: 0,
      results: [],
      error: 'Invalid startDate or endDate',
    };
  }

  const rows = await prisma.priceData.findMany({
    where: {
      symbol,
      timestamp: { gte: start, lte: end },
    },
    orderBy: { timestamp: 'asc' },
  });

  const daily = aggregateToDaily(rows);
  if (daily.length < windowDays + 1) {
    return {
      model: modelName,
      avgMAPE: 0,
      avgRMSE: 0,
      directionAccuracy: 0,
      totalPredictions: 0,
      results: [],
      error: `Not enough daily data: need at least ${windowDays + 1} days, got ${daily.length}`,
    };
  }

  const results = [];
  let sumMape = 0;
  let sumSquaredError = 0;
  let directionCorrect = 0;
  let count = 0;

  for (let startIdx = 0; startIdx <= daily.length - windowDays - 1; startIdx++) {
    const trainData = daily.slice(startIdx, startIdx + windowDays);
    const targetRow = daily[startIdx + windowDays];
    const actualPrice = targetRow.close;
    const previousClose = trainData[windowDays - 1].close;

    let predictedPrice = null;

    if (modelName === 'ensemble') {
      const [pProphet, pLgbm, pArima] = await Promise.all([
        getModelPrediction('prophet', trainData, options),
        getModelPrediction('lgbm', trainData, options),
        getModelPrediction('arima', trainData, options),
      ]);
      const prices = [
        pProphet.predicted_price,
        pLgbm.predicted_price,
        pArima.predicted_price,
      ].filter((v) => v != null && Number.isFinite(v));
      predictedPrice = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;
    } else {
      const out = await getModelPrediction(modelName, trainData, options);
      predictedPrice = out.predicted_price;
    }

    if (predictedPrice == null || !Number.isFinite(predictedPrice)) {
      continue;
    }

    const mape = actualPrice > 0 ? Math.abs((actualPrice - predictedPrice) / actualPrice) * 100 : 0;
    const se = (actualPrice - predictedPrice) ** 2;
    const actualUp = actualPrice > previousClose;
    const predictedUp = predictedPrice > previousClose;
    const directionOk = actualUp === predictedUp;

    sumMape += mape;
    sumSquaredError += se;
    if (directionOk) directionCorrect++;
    count++;

    const predictionDate = targetRow.timestamp instanceof Date ? targetRow.timestamp : new Date(targetRow.timestamp);

    await prisma.modelPrediction.create({
      data: {
        symbol,
        model_name: modelName,
        prediction_date: predictionDate,
        predicted_price: predictedPrice,
        actual_price: actualPrice,
        mape,
        direction_correct: directionOk,
      },
    });

    results.push({
      date: targetRow.date,
      predicted_price: predictedPrice,
      actual_price: actualPrice,
      mape,
      direction_correct: directionOk,
    });
  }

  const avgMAPE = count > 0 ? sumMape / count : 0;
  const avgRMSE = count > 0 ? Math.sqrt(sumSquaredError / count) : 0;
  const directionAccuracy = count > 0 ? (directionCorrect / count) * 100 : 0;

  return {
    model: modelName,
    avgMAPE,
    avgRMSE,
    directionAccuracy,
    totalPredictions: count,
    results,
  };
}

module.exports = {
  runBacktest,
  aggregateToDaily,
  getModelPrediction,
  SUPPORTED_MODELS,
  DEFAULT_WINDOW_DAYS,
};
