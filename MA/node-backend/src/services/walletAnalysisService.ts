/**
 * Multi-chain EVM wallet analysis — Alchemy SDK + CoinGecko (USD).
 * Requires ALCHEMY_API_KEY. ETHERSCAN_API_KEY is no longer used.
 */
import axios from 'axios';
import { Alchemy, AssetTransfersCategory, Network, SortingOrder, TokenBalanceType } from 'alchemy-sdk';
import type { AssetTransfersWithMetadataResult } from 'alchemy-sdk';

const COINGECKO = 'https://api.coingecko.com/api/v3';

/**
 * Son 30 gün = 720 saat (ms) — `metadata.blockTimestamp` ile `Date.now()` arası kayan pencere.
 * Base/Arbitrum USDC·USDT (6 decimal) `isForcedSixDecimals` + `applyStableUsdFallback` ile bu toplamlara dahil.
 */
const THIRTY_D_MS = 30 * 24 * 60 * 60 * 1000;
/** Son 90 gün (ms) */
const NINETY_D_MS = 90 * 24 * 60 * 60 * 1000;

/** Toplamlara dahil: sıfır miktar veya USD’si yok/ihmal edilebilir spam */
const MIN_ROLLUP_USD = 1e-10;

/** Adres bazlı 6 ondalık (USDC/USDT yanlış 18 ile bölünmesin) — küçük harf */
const ERC20_DECIMALS_6_BY_CHAIN: Record<string, Set<string>> = {
  ethereum: new Set([
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', // USDC
    '0xdac17f958d2ee523a2206206994597c13d831ec7', // USDT
  ]),
  arbitrum: new Set([
    '0xaf88d065e77c8cc2239327c5edb3a432268e5831', // USDC native
    '0xff970a61a04b1ca14834a43f5de4533ebddb5cc8', // USDC.e (bridged)
    '0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9', // USDT
  ]),
  base: new Set([
    '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', // USDC
    '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca', // USDbC (bridged)
  ]),
  polygon: new Set([
    '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359', // USDC (native)
    '0xc2132d05d31c914a87c6611c10748aeb04b58e8f', // USDT
  ]),
};

function isForcedSixDecimals(chainKey: string, contractLower: string): boolean {
  return ERC20_DECIMALS_6_BY_CHAIN[chainKey]?.has(contractLower) ?? false;
}

function stableSymbolForcesSix(symbolRaw: string): boolean {
  const s = symbolRaw.trim().toUpperCase();
  return s === 'USDC' || s === 'USDT' || s === 'USDC.E' || s === 'USD₮';
}

export type ChainKey = 'ethereum' | 'polygon' | 'arbitrum' | 'base' | 'all';

export interface ChainDef {
  key: string;
  chainId: number;
  label: string;
  nativeSymbol: string;
  cgPlatform: string;
  nativeCgId: string;
  alchemyNetwork: Network;
}

/** eth-mainnet, base-mainnet, arb-mainnet, matic-mainnet — paralel tarama */
export const WALLET_CHAINS: ChainDef[] = [
  { key: 'ethereum', chainId: 1, label: 'Ethereum', nativeSymbol: 'ETH', cgPlatform: 'ethereum', nativeCgId: 'ethereum', alchemyNetwork: Network.ETH_MAINNET },
  { key: 'base', chainId: 8453, label: 'Base', nativeSymbol: 'ETH', cgPlatform: 'base', nativeCgId: 'ethereum', alchemyNetwork: Network.BASE_MAINNET },
  { key: 'arbitrum', chainId: 42161, label: 'Arbitrum', nativeSymbol: 'ETH', cgPlatform: 'arbitrum-one', nativeCgId: 'ethereum', alchemyNetwork: Network.ARB_MAINNET },
  { key: 'polygon', chainId: 137, label: 'Polygon', nativeSymbol: 'MATIC', cgPlatform: 'polygon-pos', nativeCgId: 'matic-network', alchemyNetwork: Network.MATIC_MAINNET },
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

class RateLimiter {
  constructor(private readonly minMs: number) {}
  private last = 0;
  async throttle(): Promise<void> {
    const now = Date.now();
    const w = Math.max(0, this.minMs - (now - this.last));
    if (w) await sleep(w);
    this.last = Date.now();
  }
}

/** Zincir başına ayrı limiter: tek global gecikme tüm paralel zincirleri serileştiriyordu. */
const alchemyLimiterByNetwork = new Map<string, RateLimiter>();
function alchemyThrottle(network: Network): Promise<void> {
  const k = network as string;
  if (!alchemyLimiterByNetwork.has(k)) {
    alchemyLimiterByNetwork.set(k, new RateLimiter(75));
  }
  return alchemyLimiterByNetwork.get(k)!.throttle();
}

const cgLimiter = new RateLimiter(750);

const alchemyClients = new Map<string, Alchemy>();

function getAlchemyKey(): string {
  return String(process.env.ALCHEMY_API_KEY || '').trim();
}

function getAlchemy(network: Network): Alchemy {
  const k = network as string;
  const apiKey = getAlchemyKey();
  if (!apiKey) throw new Error('ALCHEMY_API_KEY missing');
  if (!alchemyClients.has(k)) {
    alchemyClients.set(k, new Alchemy({ apiKey, network }));
  }
  return alchemyClients.get(k)!;
}

export function isValidEvmAddress(addr: string): boolean {
  return /^0x[a-fA-F0-9]{40}$/.test(String(addr || '').trim());
}

async function fetchNativeUsd(ids: string[]): Promise<Record<string, number>> {
  const uniq = [...new Set(ids.filter(Boolean))];
  if (!uniq.length) return {};
  await cgLimiter.throttle();
  const url = `${COINGECKO}/simple/price?ids=${encodeURIComponent(uniq.join(','))}&vs_currencies=usd`;
  const { data } = await axios.get(url, { timeout: 20000 });
  const out: Record<string, number> = {};
  for (const id of uniq) {
    const usd = (data as Record<string, { usd?: number }>)[id]?.usd;
    if (typeof usd === 'number' && Number.isFinite(usd)) out[id] = usd;
  }
  return out;
}

async function fetchTokenUsdBatch(platform: string, contracts: string[]): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  const chunk = 30;
  for (let i = 0; i < contracts.length; i += chunk) {
    const part = contracts.slice(i, i + chunk);
    if (!part.length) continue;
    await cgLimiter.throttle();
    const url = `${COINGECKO}/simple/token_price/${platform}?contract_addresses=${part.join(',')}&vs_currencies=usd`;
    try {
      const { data } = await axios.get(url, { timeout: 20000 });
      const row = data as Record<string, { usd?: number }>;
      for (const [addr, v] of Object.entries(row)) {
        if (v && typeof v.usd === 'number') out[addr.toLowerCase()] = v.usd;
      }
    } catch {
      /* rate limit */
    }
  }
  return out;
}

export interface WalletAssetRow {
  symbol: string;
  chain: string;
  chainLabel: string;
  amount: number;
  usdValue: number;
  change24hPct: number | null;
  contract?: string;
  logoUri?: string | null;
}

export interface WalletTxRow {
  ts: number;
  dateIso: string;
  chain: string;
  chainLabel: string;
  tokenSymbol: string;
  /** İnsan-okunur miktar (raw ÷ 10^decimals) */
  amount: number;
  /** UI: "0.5 ETH", "100 USDC" */
  amountLabel: string;
  /** CoinGecko anlık fiyat ile yaklaşık USD */
  usdValue: number;
  direction: 'IN' | 'OUT';
  hash: string;
  type: 'native' | 'erc20';
}

export interface WalletTotals {
  /** Analizde kullanılan minimum USD eşiği (işlem + özet) */
  minUsd: number;
  portfolioUsd: number;
  in30dUsd: number;
  out30dUsd: number;
  net30dUsd: number;
  in90dUsd: number;
  out90dUsd: number;
  net90dUsd: number;
  lifetimeNetUsd: number;
}

export interface ChainWalletStat {
  chain: string;
  chainLabel: string;
  portfolioUsd: number;
  in30dUsd: number;
  out30dUsd: number;
  net30dUsd: number;
  in90dUsd: number;
  out90dUsd: number;
  net90dUsd: number;
  lifetimeNetUsd: number;
}

export interface WalletInsight {
  totalTransfersIndexed: number;
  txPerChain: Record<string, number>;
  dominantChain: string;
  tokenCount: number;
  chainsScanned: string[];
}

export interface AnalyzeResult {
  address: string;
  totals: WalletTotals;
  /** UI kaldırıldı; yanıt boyutu için boş dizi */
  assets: WalletAssetRow[];
  chainStats: ChainWalletStat[];
  transactions: WalletTxRow[];
  scannedChains: string[];
  warning: string | null;
  scannedAt: string;
  walletInsight: WalletInsight;
}

export interface AnalyzeWalletOptions {
  /** İşlem listesi ve özet kartlarında kullanılacak minimum USD (varsayılan 10) */
  minUsd?: number;
}

function normalizeMinUsd(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n) || n < 0) return 10;
  return Math.min(n, 1e9);
}

const MAX_TRANSFER_PAGES = 35;
const MAX_COUNT = 1000;
/** Ethereum / Base / Arbitrum vb. daha hızlı paralel tarama */
const CHAIN_PARALLEL = 4;

/** Zorunlu: ["external","erc20"] — USDC vb. ERC-20 için şart */
const CATEGORIES = [AssetTransfersCategory.EXTERNAL, AssetTransfersCategory.ERC20];

const MAX_DEBUG_LOGS_PER_CHAIN = 400;

function tsFromTransfer(t: AssetTransfersWithMetadataResult): number {
  const m = t.metadata?.blockTimestamp;
  if (m) {
    const ms = new Date(m).getTime();
    const x = Math.floor(ms / 1000);
    const nowSec = Math.floor(Date.now() / 1000);
    if (Number.isFinite(x) && x > 1_000_000_000 && x <= nowSec + 120) return x;
  }
  return 0;
}

function tsInRollingWindow(tsSec: number, windowMs: number, nowMs: number): boolean {
  if (tsSec <= 0) return false;
  const t = tsSec * 1000;
  return t >= nowMs - windowMs && t <= nowMs;
}

function normalizeHex(h: string | null | undefined): string | null {
  if (!h || typeof h !== 'string') return null;
  const t = h.trim();
  if (t.startsWith('0x') || t.startsWith('0X')) return t.toLowerCase();
  if (/^[0-9a-fA-F]+$/.test(t)) return `0x${t.toLowerCase()}`;
  return null;
}

function bigIntFromHex(hex: string | null | undefined): bigint | null {
  const n = normalizeHex(hex);
  if (!n || !/^0x[0-9a-fA-F]+$/.test(n)) return null;
  try {
    return BigInt(n);
  } catch {
    return null;
  }
}

/** rawContract.decimal: hex (0x12) veya düz sayı string olabilir */
function parseDecimalField(hexOrStr: string | null | undefined): number | null {
  if (hexOrStr == null || hexOrStr === '') return null;
  const s = String(hexOrStr).trim();
  if (s.startsWith('0x') || s.startsWith('0X')) {
    const n = parseInt(s, 16);
    return Number.isFinite(n) && n >= 0 ? n : null;
  }
  const n = parseInt(s, 10);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function rollupCountable(amount: number, usd: number): boolean {
  return amount > 0 && usd > MIN_ROLLUP_USD;
}

/** Bilinen ticker veya pozitif USD tahmini; aksi halde airdrop/spam */
const KNOWN_TICKERS = new Set([
  'ETH',
  'WETH',
  'USDC',
  'USDT',
  'DAI',
  'MATIC',
  'POL',
  'ARB',
  'OP',
  'WBTC',
  'BTC',
  'USDBC',
  'USDC.E',
]);

function isLikelySpam(
  parts: { amount: number; symbol: string },
  usd: number,
  cat: AssetTransfersCategory,
): boolean {
  if (parts.amount <= 0) return true;
  const raw = (parts.symbol || '').trim();
  const u = raw.toUpperCase();
  if (u === '' || u === 'TOKEN') return true;
  if (usd > MIN_ROLLUP_USD) return false;
  if (cat === AssetTransfersCategory.EXTERNAL) return false;
  if (KNOWN_TICKERS.has(u)) return false;
  if (/USDC|USDT|DAI|ETH|MATIC|ARB|BTC|WBTC|WETH/i.test(raw)) return false;
  return true;
}

/** CoinGecko fiyatı yoksa stabilcoin için ~$1 sabit (decimaller doğruysa) */
function applyStableUsdFallback(parts: { amount: number; symbol: string }, usd: number): number {
  if (usd > MIN_ROLLUP_USD) return usd;
  if (parts.amount <= 0) return usd;
  if (stableSymbolForcesSix(parts.symbol) || /USDC|USDT|DAI/i.test(parts.symbol)) {
    return parts.amount * 1;
  }
  return usd;
}

function resolveErc20Decimals(
  chainKey: string,
  contractLower: string,
  assetSymbol: string,
  rawDecimalField: string | null | undefined,
  cache: Map<string, number>,
): number {
  if (contractLower && isForcedSixDecimals(chainKey, contractLower)) return 6;
  if (stableSymbolForcesSix(assetSymbol)) return 6;
  const fromRaw = parseDecimalField(rawDecimalField);
  if (fromRaw != null) return fromRaw;
  if (contractLower && cache.has(contractLower)) return cache.get(contractLower)!;
  return 18;
}

function formatAmountLabel(amount: number, symbol: string): string {
  const s = (symbol || '?').trim() || '?';
  if (!Number.isFinite(amount) || amount === 0) return `0 ${s}`;
  let m: string;
  if (amount >= 1) {
    m = amount.toLocaleString(undefined, { maximumFractionDigits: amount >= 1000 ? 2 : 6 });
  } else if (amount >= 1e-8) {
    m = amount.toFixed(10).replace(/\.?0+$/, '');
  } else {
    m = amount.toExponential(2);
  }
  return `${m} ${s}`;
}

/**
 * Miktar: raw hex ÷ 10^decimals. USDC/USDT için 6 zorunlu (adres veya sembol + cache).
 */
function transferHumanParts(
  t: AssetTransfersWithMetadataResult,
  nativeSymbol: string,
  contractDecCache: Map<string, number>,
  chainKey: string,
): { amount: number; symbol: string; contractLower: string | null } {
  const cat = t.category;
  const rawHex = t.rawContract?.value;

  if (cat === AssetTransfersCategory.EXTERNAL) {
    let amount = 0;
    const bi = bigIntFromHex(rawHex);
    const dec = parseDecimalField(t.rawContract?.decimal) ?? 18;
    if (bi != null) {
      amount = Number(bi) / 10 ** dec;
    }
    if (amount === 0 && t.value != null) {
      amount = Math.abs(t.value);
    }
    return { amount, symbol: nativeSymbol, contractLower: null };
  }

  if (cat === AssetTransfersCategory.ERC20) {
    const addr = t.rawContract?.address?.toLowerCase() ?? '';
    const sym = (t.asset && t.asset.trim()) || 'TOKEN';
    let amount = 0;
    const bi = bigIntFromHex(rawHex);
    const dec = resolveErc20Decimals(chainKey, addr, sym, t.rawContract?.decimal, contractDecCache);
    if (bi != null) {
      amount = Number(bi) / 10 ** dec;
    }
    if (amount === 0 && t.value != null) {
      amount = Math.abs(t.value);
    }
    return { amount, symbol: sym, contractLower: addr || null };
  }

  const amount = t.value != null ? Math.abs(t.value) : 0;
  const sym = (t.asset && t.asset.trim()) || 'NFT';
  return { amount, symbol: sym, contractLower: t.rawContract?.address?.toLowerCase() ?? null };
}

async function buildContractDecimalCache(
  alchemy: Alchemy,
  network: Network,
  transfers: AssetTransfersWithMetadataResult[],
  chainKey: string,
): Promise<Map<string, number>> {
  const cache = new Map<string, number>();
  const needMeta = new Set<string>();
  for (const t of transfers) {
    if (t.category !== AssetTransfersCategory.ERC20 || !t.rawContract?.address) continue;
    const addr = t.rawContract.address.toLowerCase();
    if (isForcedSixDecimals(chainKey, addr)) {
      cache.set(addr, 6);
      continue;
    }
    const sym = (t.asset && t.asset.trim()) || '';
    if (stableSymbolForcesSix(sym)) {
      cache.set(addr, 6);
      continue;
    }
    const d = parseDecimalField(t.rawContract.decimal);
    if (d != null) {
      cache.set(addr, d);
    } else {
      needMeta.add(addr);
    }
  }
  const needList = [...needMeta].filter((a) => !cache.has(a));
  const META_BATCH = 10;
  for (let i = 0; i < needList.length; i += META_BATCH) {
    const slice = needList.slice(i, i + META_BATCH);
    await Promise.all(
      slice.map(async (addr) => {
        await alchemyThrottle(network);
        try {
          const meta = await alchemy.core.getTokenMetadata(addr);
          let d = meta.decimals != null ? Number(meta.decimals) : 18;
          if (isForcedSixDecimals(chainKey, addr)) d = 6;
          else if (stableSymbolForcesSix(meta.symbol || '')) d = 6;
          cache.set(addr, Number.isFinite(d) && d >= 0 ? d : 18);
        } catch {
          cache.set(addr, isForcedSixDecimals(chainKey, addr) ? 6 : 18);
        }
      }),
    );
  }
  return cache;
}

function transferUsdValue(
  t: AssetTransfersWithMetadataResult,
  parts: { amount: number; contractLower: string | null },
  nativeUsd: number,
  tokenPrices: Record<string, number>,
): number {
  const cat = t.category;
  if (cat === AssetTransfersCategory.EXTERNAL) {
    return parts.amount * nativeUsd;
  }
  if (cat === AssetTransfersCategory.ERC20 && parts.contractLower) {
    const p = tokenPrices[parts.contractLower] ?? 0;
    return parts.amount * p;
  }
  return 0;
}

function rowFromTransfer(
  t: AssetTransfersWithMetadataResult,
  wallet: string,
  chainKey: string,
  chainLabel: string,
  nativeSymbol: string,
  contractDecCache: Map<string, number>,
  usdValueFinal: number,
): WalletTxRow {
  const w = wallet.toLowerCase();
  const from = (t.from || '').toLowerCase();
  const to = (t.to || '').toLowerCase();
  const dir: 'IN' | 'OUT' = to === w ? 'IN' : 'OUT';
  const ts = tsFromTransfer(t);
  const parts = transferHumanParts(t, nativeSymbol, contractDecCache, chainKey);
  const amountLabel = formatAmountLabel(parts.amount, parts.symbol);
  const type: 'native' | 'erc20' =
    t.category === AssetTransfersCategory.EXTERNAL ? 'native' : 'erc20';
  return {
    ts,
    dateIso: new Date(ts * 1000).toISOString(),
    chain: chainKey,
    chainLabel,
    tokenSymbol: parts.symbol,
    amount: parts.amount,
    amountLabel,
    usdValue: usdValueFinal,
    direction: dir,
    hash: t.hash,
    type,
  };
}

async function fetchAllAssetTransfers(
  alchemy: Alchemy,
  network: Network,
  direction: 'in' | 'out',
  address: string,
): Promise<AssetTransfersWithMetadataResult[]> {
  const out: AssetTransfersWithMetadataResult[] = [];
  let pageKey: string | undefined;
  for (let page = 0; page < MAX_TRANSFER_PAGES; page++) {
    await alchemyThrottle(network);
    const base: Parameters<typeof alchemy.core.getAssetTransfers>[0] = {
      fromBlock: '0x0',
      toBlock: 'latest',
      category: CATEGORIES,
      excludeZeroValue: false,
      maxCount: MAX_COUNT,
      order: SortingOrder.ASCENDING,
      withMetadata: true,
      pageKey,
    };
    if (direction === 'in') {
      base.toAddress = address;
    } else {
      base.fromAddress = address;
    }
    const res = await alchemy.core.getAssetTransfers(base);
    const batch = (res.transfers || []) as AssetTransfersWithMetadataResult[];
    if (page === 0 && process.env.DEBUG_WALLET === '1') {
      console.log('Alchemy Data:', { direction, pageKey: res.pageKey, count: batch.length });
    }
    out.push(...batch);
    pageKey = res.pageKey;
    if (!pageKey || batch.length === 0) break;
  }
  return out;
}

async function scanOneChain(
  ch: ChainDef,
  address: string,
  nativeUsdMap: Record<string, number>,
  minUsd: number,
): Promise<{
  portfolioUsd: number;
  positionCount: number;
  txs: WalletTxRow[];
  txCount: number;
  in30: number;
  out30: number;
  in90: number;
  out90: number;
  lifeIn: number;
  lifeOut: number;
}> {
  const alchemy = getAlchemy(ch.alchemyNetwork);
  const network = ch.alchemyNetwork;
  const nativeUsd = nativeUsdMap[ch.nativeCgId] || 0;

  await alchemyThrottle(network);
  const balWei = await alchemy.core.getBalance(address);
  const nativeAmt = Number(balWei.toString()) / 1e18;
  const nativeUsdVal = nativeAmt * nativeUsd;
  let portfolioUsd = nativeUsdVal;
  let positionCount = 0;
  if (nativeAmt > 1e-12 || nativeUsdVal > 0.005) positionCount += 1;

  let tokenBalancesPage: string | undefined;
  const balanceByContract = new Map<string, string>();
  do {
    await alchemyThrottle(network);
    const tb = await alchemy.core.getTokenBalances(address, {
      type: TokenBalanceType.ERC20,
      pageKey: tokenBalancesPage,
    });
    for (const row of tb.tokenBalances || []) {
      if (row.error || row.tokenBalance == null) continue;
      const c = row.contractAddress.toLowerCase();
      balanceByContract.set(c, row.tokenBalance);
    }
    tokenBalancesPage = (tb as { pageKey?: string }).pageKey;
  } while (tokenBalancesPage);

  const contracts = [...balanceByContract.keys()];

  const [incoming, outgoing] = await Promise.all([
    fetchAllAssetTransfers(alchemy, network, 'in', address),
    fetchAllAssetTransfers(alchemy, network, 'out', address),
  ]);

  const seen = new Set<string>();
  const merged: AssetTransfersWithMetadataResult[] = [];
  for (const t of [...incoming, ...outgoing]) {
    const id = t.uniqueId || `${t.hash}-${t.blockNum}`;
    if (seen.has(id)) continue;
    seen.add(id);
    merged.push(t);
  }

  const txErc20 = new Set<string>();
  for (const t of merged) {
    if (t.category === AssetTransfersCategory.ERC20 && t.rawContract?.address) {
      txErc20.add(t.rawContract.address.toLowerCase());
    }
  }
  const allPriceContracts = [...new Set([...contracts, ...txErc20])];
  const tokenPrices = await fetchTokenUsdBatch(ch.cgPlatform, allPriceContracts);

  const META_PAGE = 12;
  for (let i = 0; i < contracts.length; i += META_PAGE) {
    const slice = contracts.slice(i, i + META_PAGE);
    const rows = await Promise.all(
      slice.map(async (contract) => {
        await alchemyThrottle(network);
        let meta: { name: string | null; symbol: string | null; decimals: number | null; logo: string | null };
        try {
          meta = await alchemy.core.getTokenMetadata(contract);
        } catch {
          meta = { name: null, symbol: null, decimals: 18, logo: null };
        }
        const hexBal = balanceByContract.get(contract);
        if (!hexBal) return null;
        const cLow = contract.toLowerCase();
        let dec = meta.decimals ?? 18;
        if (isForcedSixDecimals(ch.key, cLow)) dec = 6;
        else if (stableSymbolForcesSix(meta.symbol || '')) dec = 6;
        const raw = BigInt(hexBal);
        const amt = Number(raw) / 10 ** dec;
        if (amt <= 1e-12) return null;
        const pu = tokenPrices[contract.toLowerCase()] ?? 0;
        return amt * pu;
      }),
    );
    for (const u of rows) {
      if (u != null) {
        portfolioUsd += u;
        positionCount += 1;
      }
    }
  }

  const contractDecCache = await buildContractDecimalCache(alchemy, network, merged, ch.key);

  const priceForRow = { ...tokenPrices };
  const nowMs = Date.now();

  const txs: WalletTxRow[] = [];
  let in30 = 0;
  let out30 = 0;
  let in90 = 0;
  let out90 = 0;
  let lifeIn = 0;
  let lifeOut = 0;

  const w = address.toLowerCase();
  let debugLogs = 0;

  for (const t of merged) {
    const from = (t.from || '').toLowerCase();
    const to = (t.to || '').toLowerCase();
    const selfLoop = from === to && from === w;
    const parts = transferHumanParts(t, ch.nativeSymbol, contractDecCache, ch.key);
    const usdRaw = transferUsdValue(t, parts, nativeUsd, priceForRow);
    const usd = applyStableUsdFallback(parts, usdRaw);
    const ts = tsFromTransfer(t);
    const cat = t.category;

    if (
      process.env.DEBUG_WALLET === '1' &&
      !selfLoop &&
      !isLikelySpam(parts, usd, cat) &&
      debugLogs < MAX_DEBUG_LOGS_PER_CHAIN
    ) {
      console.log('Bulunan İşlem:', ch.label, parts.symbol, parts.amount, usd);
      debugLogs += 1;
    }

    if (selfLoop) continue;
    if (isLikelySpam(parts, usd, cat)) continue;
    if (usd < minUsd) continue;

    txs.push(rowFromTransfer(t, address, ch.key, ch.label, ch.nativeSymbol, contractDecCache, usd));

    const in30win = tsInRollingWindow(ts, THIRTY_D_MS, nowMs);
    const in90win = tsInRollingWindow(ts, NINETY_D_MS, nowMs);

    if (to === w) {
      lifeIn += usd;
      if (in30win) in30 += usd;
      if (in90win) in90 += usd;
    }
    if (from === w) {
      lifeOut += usd;
      if (in30win) out30 += usd;
      if (in90win) out90 += usd;
    }
  }

  return {
    portfolioUsd,
    positionCount,
    txs,
    txCount: merged.length,
    in30,
    out30,
    in90,
    out90,
    lifeIn,
    lifeOut,
  };
}

export async function analyzeWallet(
  address: string,
  chainFilter: ChainKey | 'all' = 'all',
  options: AnalyzeWalletOptions = {},
): Promise<AnalyzeResult> {
  const addr = address.trim().toLowerCase();
  if (!isValidEvmAddress(addr)) throw new Error('Invalid EVM address');

  const minUsd = normalizeMinUsd(options.minUsd ?? 10);

  const apiKey = getAlchemyKey();
  if (!apiKey) {
    return {
      address: addr,
      totals: {
        minUsd,
        portfolioUsd: 0,
        in30dUsd: 0,
        out30dUsd: 0,
        net30dUsd: 0,
        in90dUsd: 0,
        out90dUsd: 0,
        net90dUsd: 0,
        lifetimeNetUsd: 0,
      },
      assets: [],
      chainStats: [],
      transactions: [],
      scannedChains: [],
      warning:
        'ALCHEMY_API_KEY tanımlı değil. node-backend .env dosyasına Alchemy Dashboard anahtarını ekleyin.',
      scannedAt: new Date().toISOString(),
      walletInsight: {
        totalTransfersIndexed: 0,
        txPerChain: {},
        dominantChain: '—',
        tokenCount: 0,
        chainsScanned: [],
      },
    };
  }
  if (apiKey.startsWith('sk-ant-')) {
    return {
      address: addr,
      totals: {
        minUsd,
        portfolioUsd: 0,
        in30dUsd: 0,
        out30dUsd: 0,
        net30dUsd: 0,
        in90dUsd: 0,
        out90dUsd: 0,
        net90dUsd: 0,
        lifetimeNetUsd: 0,
      },
      assets: [],
      chainStats: [],
      transactions: [],
      scannedChains: [],
      warning:
        'ALCHEMY_API_KEY geçersiz: sk-ant- ile başlayan değer Anthropic (LLM) anahtarıdır, Alchemy değil. https://dashboard.alchemy.com/ üzerindeki Alchemy API key’i .env dosyasına yapıştırın.',
      scannedAt: new Date().toISOString(),
      walletInsight: {
        totalTransfersIndexed: 0,
        txPerChain: {},
        dominantChain: '—',
        tokenCount: 0,
        chainsScanned: [],
      },
    };
  }

  const chains =
    chainFilter === 'all' ? WALLET_CHAINS : WALLET_CHAINS.filter((c) => c.key === chainFilter);

  const nativeIds = chains.map((c) => c.nativeCgId);
  const nativeUsdMap = await fetchNativeUsd(nativeIds);

  const allTxs: WalletTxRow[] = [];
  const txPerChain: Record<string, number> = {};
  const chainStats: ChainWalletStat[] = [];
  let sumIn30 = 0;
  let sumOut30 = 0;
  let sumIn90 = 0;
  let sumOut90 = 0;
  let sumLifeIn = 0;
  let sumLifeOut = 0;
  let sumPortfolio = 0;
  let sumPositions = 0;

  for (let i = 0; i < chains.length; i += CHAIN_PARALLEL) {
    const batch = chains.slice(i, i + CHAIN_PARALLEL);
    const results = await Promise.all(
      batch.map((ch) =>
        scanOneChain(ch, addr, nativeUsdMap, minUsd).catch((e) => {
          console.warn(`[wallet/alchemy] ${ch.key}:`, e);
          return {
            portfolioUsd: 0,
            positionCount: 0,
            txs: [] as WalletTxRow[],
            txCount: 0,
            in30: 0,
            out30: 0,
            in90: 0,
            out90: 0,
            lifeIn: 0,
            lifeOut: 0,
          };
        }),
      ),
    );
    for (let j = 0; j < batch.length; j++) {
      const ch = batch[j];
      const r = results[j];
      allTxs.push(...r.txs);
      txPerChain[ch.key] = r.txCount;
      sumPortfolio += r.portfolioUsd;
      sumPositions += r.positionCount;
      sumIn30 += r.in30;
      sumOut30 += r.out30;
      sumIn90 += r.in90;
      sumOut90 += r.out90;
      sumLifeIn += r.lifeIn;
      sumLifeOut += r.lifeOut;
      chainStats.push({
        chain: ch.key,
        chainLabel: ch.label,
        portfolioUsd: r.portfolioUsd,
        in30dUsd: r.in30,
        out30dUsd: r.out30,
        net30dUsd: r.in30 - r.out30,
        in90dUsd: r.in90,
        out90dUsd: r.out90,
        net90dUsd: r.in90 - r.out90,
        lifetimeNetUsd: r.lifeIn - r.lifeOut,
      });
    }
  }

  allTxs.sort((a, b) => b.ts - a.ts);
  const transactions = allTxs.slice(0, 8000);

  const dominantChain = Object.entries(txPerChain).sort((a, b) => b[1] - a[1])[0]?.[0] || '—';

  const walletInsight: WalletInsight = {
    totalTransfersIndexed: allTxs.length,
    txPerChain,
    dominantChain,
    tokenCount: sumPositions,
    chainsScanned: chains.map((c) => c.key),
  };

  return {
    address: addr,
    totals: {
      minUsd,
      portfolioUsd: sumPortfolio,
      in30dUsd: sumIn30,
      out30dUsd: sumOut30,
      net30dUsd: sumIn30 - sumOut30,
      in90dUsd: sumIn90,
      out90dUsd: sumOut90,
      net90dUsd: sumIn90 - sumOut90,
      lifetimeNetUsd: sumLifeIn - sumLifeOut,
    },
    assets: [],
    chainStats,
    transactions,
    scannedChains: chains.map((c) => c.key),
    warning: null,
    scannedAt: new Date().toISOString(),
    walletInsight,
  };
}

export function buildLlmContext(summary: AnalyzeResult, maxChars = 12000): string {
  const wi = summary.walletInsight;
  const lines: string[] = [];
  lines.push(`Address: ${summary.address}`);
  lines.push(
    `Min USD filter: ${summary.totals.minUsd.toFixed(2)} — Portfolio: ${summary.totals.portfolioUsd.toFixed(2)}, 30d In: ${summary.totals.in30dUsd.toFixed(2)}, 30d Out: ${summary.totals.out30dUsd.toFixed(2)}, 30d Net: ${summary.totals.net30dUsd.toFixed(2)}, 90d In: ${summary.totals.in90dUsd.toFixed(2)}, 90d Out: ${summary.totals.out90dUsd.toFixed(2)}, 90d Net: ${summary.totals.net90dUsd.toFixed(2)}, Lifetime net: ${summary.totals.lifetimeNetUsd.toFixed(2)}`,
  );
  lines.push(
    'Rules: categories external+erc20 only; 30d/90d windows use metadata.blockTimestamp vs now; IN=to wallet OUT=from wallet; min USD applies to list and rollups; USDC/USDT forced 6 decimals on Base/Arbitrum etc.; spam/no-price excluded.',
  );
  lines.push(
    `Activity — Indexed transfers: ${wi.totalTransfersIndexed}, Dominant chain (by tx count): ${wi.dominantChain}, Balance positions (native+ERC20): ${wi.tokenCount}`,
  );
  lines.push(`Tx per chain: ${JSON.stringify(wi.txPerChain)}`);
  if (summary.chainStats.length) {
    lines.push('Per-chain (portfolio / 30d / 90d / lifetime net):');
    for (const c of summary.chainStats) {
      lines.push(
        `- ${c.chainLabel}: portfolio $${c.portfolioUsd.toFixed(2)} | 30d net $${c.net30dUsd.toFixed(2)} | 90d net $${c.net90dUsd.toFixed(2)} | life net $${c.lifetimeNetUsd.toFixed(2)}`,
      );
    }
  }
  if (summary.warning) lines.push(`Warning: ${summary.warning}`);
  lines.push('Recent transfers (newest first, sample; amount = human token units):');
  for (const t of summary.transactions.slice(0, 40)) {
    lines.push(
      `- ${t.dateIso} | ${t.chainLabel} | ${t.amountLabel} | ~$${t.usdValue.toFixed(4)} | ${t.direction} | ${t.hash}`,
    );
  }
  const text = lines.join('\n');
  return text.length > maxChars ? text.slice(0, maxChars) + '\n...[truncated]' : text;
}

/** Chat / WalletAgent için yapılandırılmış özet (yanlış üretimi azaltmak için) */
export interface WalletContextPayload {
  version: 1;
  address: string;
  scannedAt: string;
  totals: WalletTotals;
  chainStats: ChainWalletStat[];
  walletInsight: WalletInsight;
}

export function buildWalletContext(summary: AnalyzeResult): WalletContextPayload {
  return {
    version: 1,
    address: summary.address,
    scannedAt: summary.scannedAt,
    totals: summary.totals,
    chainStats: summary.chainStats,
    walletInsight: summary.walletInsight,
  };
}
