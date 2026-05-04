import axios from 'axios';
import type { PrismaClient } from '@prisma/client';
import { Prisma } from '@prisma/client';

const BINANCE_BASE_URL = 'https://api.binance.com';

const HTTP_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  Accept: 'application/json',
};

export type OHLCVCandle = {
  openTime: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

/** BTC/USDT veya BTCUSDT → BTCUSDT */
export function normalizeSymbol(symbol: string): string {
  return symbol.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
}

/**
 * Binance GET /api/v3/klines — public, API key gerekmez.
 * 1000 mumdan fazlası için sayfalama yapılır.
 */
export async function fetchHistoricalOHLCV(
  symbol: string,
  startDate: string,
  endDate: string,
  interval: string = '1d'
): Promise<OHLCVCandle[]> {
  const sym = normalizeSymbol(symbol);
  const startMs = Date.parse(`${startDate}T00:00:00.000Z`);
  const endMs = Date.parse(`${endDate}T23:59:59.999Z`);

  if (Number.isNaN(startMs) || Number.isNaN(endMs)) {
    throw new Error('startDate veya endDate geçersiz tarih formatında');
  }
  if (startMs >= endMs) {
    throw new Error('startDate, endDate tarihinden küçük olmalıdır');
  }

  const all: OHLCVCandle[] = [];
  let cursor = startMs;
  const maxLimit = 1000;

  while (cursor <= endMs) {
    const { data } = await axios.get(`${BINANCE_BASE_URL}/api/v3/klines`, {
      params: {
        symbol: sym,
        interval,
        startTime: cursor,
        endTime: endMs,
        limit: maxLimit,
      },
      headers: HTTP_HEADERS,
      timeout: 30000,
      validateStatus: (s) => s === 200,
    });

    const klines = data as unknown[];
    if (!Array.isArray(klines) || klines.length === 0) {
      break;
    }

    for (const k of klines) {
      const row = k as number[];
      const safe = (v: unknown) => {
        const n = parseFloat(String(v));
        return Number.isFinite(n) ? n : 0;
      };
      all.push({
        openTime: new Date(row[0]),
        open: safe(row[1]),
        high: safe(row[2]),
        low: safe(row[3]),
        close: safe(row[4]),
        volume: safe(row[5]),
      });
    }

    const lastOpen = (klines[klines.length - 1] as number[])[0];
    cursor = lastOpen + 1;
    if (klines.length < maxLimit) {
      break;
    }
  }

  return all;
}

function distinctDayCount(rows: { timestamp: Date }[]): number {
  return new Set(rows.map((r) => r.timestamp.toISOString().slice(0, 10))).size;
}

/** SQLite: tek sorguda parametre limiti (~999) — parçalı yaz */
const INSERT_CHUNK = 80;

export type PriceDataInsertRow = {
  symbol: string;
  timestamp: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

function dedupePriceRows(rows: PriceDataInsertRow[]): PriceDataInsertRow[] {
  const m = new Map<string, PriceDataInsertRow>();
  for (const r of rows) {
    m.set(`${r.symbol}|${r.timestamp.getTime()}`, r);
  }
  return [...m.values()];
}

/**
 * SQLite + Prisma: `createMany({ skipDuplicates })` desteklenmiyor (Unknown argument).
 * INSERT OR IGNORE ile toplu yazım + changes() ile eklenen satır sayısı.
 */
export async function priceDataCreateManyChunked(
  prisma: PrismaClient,
  rows: PriceDataInsertRow[]
): Promise<number> {
  const deduped = dedupePriceRows(rows);
  let total = 0;
  for (let i = 0; i < deduped.length; i += INSERT_CHUNK) {
    const chunk = deduped.slice(i, i + INSERT_CHUNK);
    const values = chunk.map(
      (r) =>
        Prisma.sql`(${r.symbol}, ${r.timestamp}, ${r.open}, ${r.high}, ${r.low}, ${r.close}, ${r.volume})`
    );
    await prisma.$transaction(async (tx) => {
      await tx.$executeRaw`
        INSERT OR IGNORE INTO "PriceData" ("symbol", "timestamp", "open", "high", "low", "close", "volume")
        VALUES ${Prisma.join(values, ', ')}
      `;
      const out = await tx.$queryRaw<Array<{ c: bigint | number }>>`SELECT changes() AS c`;
      total += Number(out[0]?.c ?? 0);
    });
  }
  return total;
}

/**
 * Backtest için yeterli günlük mum yoksa Binance'ten çekip price_data'ya yazar.
 * interval=1d (motor aggregateToDaily ile uyumlu).
 */
export async function ensurePriceDataForBacktest(
  prisma: PrismaClient,
  symbol: string,
  startDate: string,
  endDate: string,
  windowDays: number
): Promise<{ inserted: number; fetched: number }> {
  const norm = normalizeSymbol(symbol);
  const start = new Date(`${startDate}T00:00:00.000Z`);
  const end = new Date(`${endDate}T23:59:59.999Z`);

  const existing = await prisma.priceData.findMany({
    where: { symbol: norm, timestamp: { gte: start, lte: end } },
    orderBy: { timestamp: 'asc' },
  });

  const minDays = windowDays + 1;
  const daysOk = distinctDayCount(existing) >= minDays && existing.length >= minDays;

  if (daysOk) {
    return { inserted: 0, fetched: 0 };
  }

  const candles = await fetchHistoricalOHLCV(norm, startDate, endDate, '1d');
  if (!candles.length) {
    throw new Error(
      'Binance geçmiş veri döndürmedi. Tarih aralığını (geçmişe dönük) ve sembolü kontrol edin.'
    );
  }

  const rows = candles.map((c) => ({
    symbol: norm,
    timestamp: c.openTime,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }));

  const inserted = await priceDataCreateManyChunked(prisma, rows);

  return { inserted, fetched: candles.length };
}
