import path from 'path';
import { Request, Response } from 'express';
import { prisma } from '../db/prismaClient';
import {
  fetchHistoricalOHLCV,
  ensurePriceDataForBacktest,
  normalizeSymbol,
  priceDataCreateManyChunked,
} from '../services/binanceBacktestService';

// Backtest engine lives in backend/backtest (sibling to node-backend)
const backtestEnginePath = path.join(__dirname, '..', '..', '..', 'backend', 'backtest', 'backtestEngine.js');
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { runBacktest, SUPPORTED_MODELS } = require(backtestEnginePath);

export async function collectBacktestData(req: Request, res: Response) {
  try {
    const { symbol, startDate, endDate, interval } = req.body || {};

    if (!symbol || !startDate || !endDate) {
      return res.status(400).json({
        error: 'symbol, startDate ve endDate zorunludur',
      });
    }

    const sym = normalizeSymbol(symbol);
    const candles = await fetchHistoricalOHLCV(
      sym,
      startDate,
      endDate,
      interval || '1d',
    );

    if (!candles.length) {
      return res.status(200).json({
        message: 'Belirtilen aralık için veri bulunamadı',
        inserted: 0,
      });
    }

    const dataToInsert = candles.map((c) => ({
      symbol: sym,
      timestamp: c.openTime,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
    }));

    const inserted = await priceDataCreateManyChunked(prisma, dataToInsert);

    return res.status(201).json({
      message: 'Veri başarıyla toplandı ve kaydedildi',
      requested: dataToInsert.length,
      inserted,
    });
  } catch (err: any) {
    console.error('collectBacktestData error', err);
    return res.status(500).json({
      error: 'Veri toplama sırasında bir hata oluştu',
      details: err?.message,
    });
  }
}

export async function runBacktestHandler(req: Request, res: Response) {
  try {
    const { symbol, models, startDate, endDate, windowDays } = req.body || {};

    if (!symbol || !startDate || !endDate) {
      return res.status(400).json({
        error: 'symbol, startDate ve endDate zorunludur',
      });
    }

    const modelList = Array.isArray(models) && models.length > 0
      ? models
      : ['arima'];

    const invalid = modelList.filter((m: string) => !SUPPORTED_MODELS.includes(m));
    if (invalid.length > 0) {
      return res.status(400).json({
        error: `Desteklenmeyen model(ler): ${invalid.join(', ')}. Desteklenen: ${SUPPORTED_MODELS.join(', ')}`,
      });
    }

    const win = typeof windowDays === 'number' && windowDays > 0 ? windowDays : 30;

    try {
      await ensurePriceDataForBacktest(prisma, symbol, startDate, endDate, win);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('ensurePriceDataForBacktest', e);
      return res.status(502).json({
        error: 'Binance geçmiş verisi alınamadı veya kaydedilemedi',
        details: msg,
      });
    }

    const pythonBackendUrl = process.env.PYTHON_BACKEND_URL || process.env.PYTHON_BACKTEST_API || '';

    const results: Array<{
      model: string;
      avgMAPE: number;
      avgRMSE: number;
      directionAccuracy: number;
      totalPredictions: number;
      results: unknown[];
      error?: string;
    }> = [];

    for (const modelName of modelList) {
      const summary = await runBacktest(
        prisma,
        {
          symbol: normalizeSymbol(symbol),
          modelName,
          startDate,
          endDate,
          windowDays: win,
        },
        { pythonBackendUrl: pythonBackendUrl || undefined },
      );
      results.push(summary);
    }

    return res.status(200).json({
      symbol,
      startDate,
      endDate,
      models: modelList,
      summaries: results,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('runBacktest error', err);
    return res.status(500).json({
      error: 'Backtest çalıştırılırken bir hata oluştu',
      details: message,
    });
  }
}

