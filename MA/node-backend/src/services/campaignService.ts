/**
 * Kampanya / fırsat toplama: Galxe GraphQL, Layer3 (kısıtlı), yeni listeler, Nitter RSS.
 * Cache: 30 dk (node-cache). newsService ile aynı genel desen.
 */

import { createHash } from 'crypto';
import axios from 'axios';
import Parser from 'rss-parser';
import NodeCache from 'node-cache';

const CACHE_TTL_SEC = 30 * 60;
const cache = new NodeCache({ stdTTL: CACHE_TTL_SEC });

const HTTP = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  Accept: 'application/json, text/xml, application/rss+xml, */*',
};

const GALXE_ENDPOINT = 'https://graphigo.prd.galaxy.eco/query';
const GALXE_SPACES = ['galxe', 'bnbchain', 'base', 'arbitrum', 'optimism'];

const CMC_NEW_URL = 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing/new';
const COINPAPRIKA_COINS = 'https://api.coinpaprika.com/v1/coins';

const NITTER_FEEDS = [
  'https://nitter.net/Galxe/rss',
  'https://nitter.net/layer3xyz/rss',
  'https://nitter.net/gleamio/rss',
  'https://nitter.net/binance/rss',
  'https://nitter.net/CoinMarketCap/rss',
];

const GALXE_LIST_QUERY = `
query CampaignList($alias: String!, $campaignInput: ListCampaignInput!) {
  space(alias: $alias) {
    id
    name
    campaigns(input: $campaignInput) {
      list {
        id
        name
        description
        startTime
        endTime
        type
      }
    }
  }
}
`;

export type CampaignSource = 'galxe' | 'layer3' | 'coinmarketcap' | 'nitter';

export type CampaignTypeTag =
  | 'AIRDROP'
  | 'TESTNET'
  | 'AI_CONTENT'
  | 'NFT_MINT'
  | 'REFERRAL'
  | 'LAUNCH'
  | 'OTHER';

export interface CampaignItem {
  id: string;
  source: CampaignSource;
  title: string;
  description?: string;
  url: string;
  startTime?: string;
  endTime?: string;
  rewardType?: string;
  rewardAmount?: string;
  /** Nitter */
  text?: string;
  author?: string;
  publishedAt?: string;
  /** Yeni listeleme */
  dateAdded?: string;
  typeTag: CampaignTypeTag;
  importanceScore: number;
}

const rssParser = new Parser();

function inferTypeTag(text: string): CampaignTypeTag {
  const t = text.toLowerCase();
  if (t.includes('airdrop')) return 'AIRDROP';
  if (t.includes('testnet')) return 'TESTNET';
  if (/\bai\b/.test(t) || t.includes('content')) return 'AI_CONTENT';
  if (t.includes('mint')) return 'NFT_MINT';
  if (t.includes('referral')) return 'REFERRAL';
  if (t.includes('launch') || t.includes('listing')) return 'LAUNCH';
  return 'OTHER';
}

function extractRewardHint(text: string): string {
  const m = text.match(/\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:USDT|ETH|USD|BTC|SOL|MATIC|ARB|OP)/i);
  return m ? m[0].replace(/,/g, '') : '';
}

function parseRewardNumber(text: string, rewardAmount?: string): number {
  const raw = `${rewardAmount || ''} ${text}`;
  const m = raw.match(/\$?\s*([\d,.]+)\s*(k|m)?/i);
  if (!m) return 0;
  let n = parseFloat(m[1].replace(/,/g, ''));
  if (Number.isNaN(n)) return 0;
  const mult = m[2]?.toLowerCase();
  if (mult === 'k') n *= 1000;
  if (mult === 'm') n *= 1_000_000;
  return n;
}

function computeImportanceScore(item: Omit<CampaignItem, 'importanceScore'>): number {
  let score = 0;
  const blob = `${item.title} ${item.description || ''} ${item.text || ''}`.toLowerCase();
  const rewardN = parseRewardNumber(blob, item.rewardAmount);

  if (rewardN >= 10_000) score += 30;
  else if (rewardN >= 1000) score += 22;
  else if (rewardN >= 100) score += 15;
  else if (rewardN >= 10) score += 8;

  const end = item.endTime ? new Date(item.endTime) : null;
  const now = Date.now();
  if (end && end.getTime() > now && end.getTime() - now < 3 * 86400_000) score += 25;

  if (item.typeTag === 'AI_CONTENT') score += 20;

  if (item.source === 'coinmarketcap') score += 15;

  if (item.source === 'galxe' || item.source === 'layer3') score += 10;

  return Math.min(100, Math.round(score));
}

function finalizeItem(partial: Omit<CampaignItem, 'importanceScore' | 'typeTag'>): CampaignItem {
  const typeTag = inferTypeTag(
    `${partial.title} ${partial.description || ''} ${partial.text || ''} ${partial.rewardType || ''}`
  );
  const withTag: Omit<CampaignItem, 'importanceScore'> = { ...partial, typeTag };
  return { ...withTag, importanceScore: computeImportanceScore(withTag) };
}

async function fetchGalxeCampaigns(): Promise<CampaignItem[]> {
  const out: CampaignItem[] = [];
  const seen = new Set<string>();

  const campaignInput = {
    forAdmin: false,
    first: 12,
    after: '-1',
    excludeChildren: true,
    statuses: ['Active'],
    listType: 'Newest',
    types: [
      'Drop',
      'MysteryBox',
      'Airdrop',
      'Token',
      'Bounty',
      'Oat',
      'Points',
      'ExternalLink',
      'OptIn',
      'Mintlist',
      'PowahDrop',
      'Parent',
    ],
    searchString: null,
    gasTypes: null,
    credSources: null,
    rewardTypes: null,
    chains: null,
  };

  for (const alias of GALXE_SPACES) {
    try {
      const { data } = await axios.post(
        GALXE_ENDPOINT,
        {
          query: GALXE_LIST_QUERY,
          variables: { alias, campaignInput },
        },
        { headers: { ...HTTP, 'Content-Type': 'application/json' }, timeout: 25000 }
      );

      const list = data?.data?.space?.campaigns?.list;
      if (!Array.isArray(list)) continue;

      for (const c of list) {
        if (!c?.id || seen.has(c.id)) continue;
        seen.add(c.id);
        const desc = (c.description || '').replace(/\s+/g, ' ').trim();
        const startSec = typeof c.startTime === 'number' ? c.startTime : 0;
        const endSec = typeof c.endTime === 'number' ? c.endTime : null;
        const startTime = startSec ? new Date(startSec * 1000).toISOString() : undefined;
        const endTime = endSec ? new Date(endSec * 1000).toISOString() : undefined;
        const hint = extractRewardHint(`${desc} ${c.name || ''}`);

        const partial: Omit<CampaignItem, 'importanceScore' | 'typeTag'> = {
          id: `galxe-${c.id}`,
          source: 'galxe',
          title: c.name || c.id,
          description: desc || undefined,
          // Galxe app: /quest/{spaceAlias}/{campaignHash} — tek segmentli /quest/{id} 404 veriyor
          url: `https://app.galxe.com/quest/${encodeURIComponent(alias)}/${encodeURIComponent(c.id)}`,
          startTime,
          endTime,
          rewardType: c.type || undefined,
          rewardAmount: hint || undefined,
        };
        out.push(finalizeItem(partial));
      }
    } catch (e) {
      console.warn(`[campaignService] Galxe space ${alias}:`, (e as Error).message);
    }
  }

  return out;
}

/** Layer3 app Cloudflare ile çoğu sunucuda engellenir; şimdilik boş. */
async function fetchLayer3Quests(): Promise<CampaignItem[]> {
  try {
    const { status } = await axios.get('https://layer3.xyz/quests', {
      timeout: 12000,
      headers: HTTP,
      validateStatus: () => true,
    });
    if (status !== 200) {
      console.warn('[campaignService] Layer3: ana sayfa HTTP', status);
    }
  } catch (e) {
    console.warn('[campaignService] Layer3:', (e as Error).message);
  }
  return [];
}

interface PaprikaCoinRow {
  id: string;
  name: string;
  symbol: string;
  is_new?: boolean;
}

async function fetchCoinpaprikaNewListings(): Promise<CampaignItem[]> {
  try {
    const { data } = await axios.get<PaprikaCoinRow[]>(COINPAPRIKA_COINS, {
      timeout: 25000,
      headers: HTTP,
    });
    const fresh = (data || []).filter((c) => c.is_new).slice(0, 25);

    const details = await Promise.all(
      fresh.map(async (c) => {
        try {
          const { data: detail } = await axios.get(
            `https://api.coinpaprika.com/v1/coins/${encodeURIComponent(c.id)}`,
            { timeout: 10000, headers: HTTP }
          );
          const dateAdded = detail?.first_data_at
            ? new Date(detail.first_data_at).toISOString()
            : undefined;
          return { coin: c, dateAdded };
        } catch {
          return { coin: c, dateAdded: undefined as string | undefined };
        }
      })
    );

    return details.map(({ coin: c, dateAdded }) => {
      const partial: Omit<CampaignItem, 'importanceScore' | 'typeTag'> = {
        id: `cmc-${c.symbol}-${c.id}`,
        source: 'coinmarketcap',
        title: `New listing: ${c.name} (${c.symbol})`,
        description: 'Recently listed token (CMC public endpoint kapalıysa Coinpaprika yedek).',
        url: `https://coinpaprika.com/coin/${encodeURIComponent(c.id)}`,
        dateAdded,
        publishedAt: dateAdded,
      };
      return finalizeItem(partial);
    });
  } catch (e) {
    console.warn('[campaignService] Coinpaprika:', (e as Error).message);
    return [];
  }
}

/** CMC public endpoint — çalışırsa kullan, değilse Coinpaprika. */
async function fetchCoinmarketcapNewListings(): Promise<CampaignItem[]> {
  try {
    const { data, status } = await axios.get(CMC_NEW_URL, {
      params: { limit: 30, start: 1 },
      timeout: 20000,
      headers: {
        ...HTTP,
        Origin: 'https://coinmarketcap.com',
        Referer: 'https://coinmarketcap.com/',
      },
      validateStatus: () => true,
    });
    if (status !== 200 || !data?.data?.cryptoCurrencyList) {
      return fetchCoinpaprikaNewListings();
    }

    const list = data.data.cryptoCurrencyList as Array<{
      name: string;
      symbol: string;
      slug: string;
      dateAdded: string;
    }>;

    return list.map((c) => {
      const partial: Omit<CampaignItem, 'importanceScore' | 'typeTag'> = {
        id: `cmc-${c.symbol}-${c.slug}`,
        source: 'coinmarketcap',
        title: `New listing: ${c.name} (${c.symbol})`,
        url: `https://coinmarketcap.com/currencies/${c.slug}/`,
        dateAdded: c.dateAdded,
        publishedAt: c.dateAdded ? new Date(c.dateAdded).toISOString() : undefined,
      };
      return finalizeItem(partial);
    });
  } catch {
    return fetchCoinpaprikaNewListings();
  }
}

async function fetchRssXml(url: string): Promise<string> {
  const { data, status } = await axios.get<string>(url, {
    timeout: 18000,
    headers: { ...HTTP, Accept: 'application/rss+xml, application/xml, text/xml, */*' },
    responseType: 'text',
    validateStatus: (s) => s >= 200 && s < 400,
  });
  if (status !== 200) throw new Error(`HTTP ${status}`);
  return typeof data === 'string' ? data : String(data);
}

async function fetchNitterFeeds(): Promise<CampaignItem[]> {
  const out: CampaignItem[] = [];
  for (const feedUrl of NITTER_FEEDS) {
    try {
      const xml = await fetchRssXml(feedUrl);
      const parsed = await rssParser.parseString(xml);
      const author = parsed.title?.split('/ @')?.[1]?.trim() || 'unknown';

      for (const item of parsed.items || []) {
        const link = item.link || '';
        const guid = item.guid || link || `${item.title}-${item.pubDate}`;
        const id = `nitter-${createHash('sha256').update(String(guid)).digest('hex').slice(0, 32)}`;

        const text = item.title || item.contentSnippet || item.content || '';
        const partial: Omit<CampaignItem, 'importanceScore' | 'typeTag'> = {
          id,
          source: 'nitter',
          title: (item.title || 'Tweet').slice(0, 200),
          text: text.slice(0, 2000),
          description: text.slice(0, 500),
          url: link || feedUrl,
          author,
          publishedAt: item.pubDate ? new Date(item.pubDate).toISOString() : new Date().toISOString(),
        };
        out.push(finalizeItem(partial));
      }
    } catch (e) {
      console.warn(`[campaignService] Nitter ${feedUrl}:`, (e as Error).message);
    }
  }
  return out;
}

async function fetchAllCampaigns(): Promise<CampaignItem[]> {
  const [galxe, layer3, cmc, nitter] = await Promise.all([
    fetchGalxeCampaigns(),
    fetchLayer3Quests(),
    fetchCoinmarketcapNewListings(),
    fetchNitterFeeds(),
  ]);

  const merged = [...galxe, ...layer3, ...cmc, ...nitter];
  merged.sort((a, b) => b.importanceScore - a.importanceScore || (b.publishedAt || '').localeCompare(a.publishedAt || ''));
  return merged;
}

export async function getCampaigns(): Promise<CampaignItem[]> {
  const cacheKey = 'campaigns:all:v2';
  const hit = cache.get<CampaignItem[]>(cacheKey);
  if (hit) return hit;

  const data = await fetchAllCampaigns();
  cache.set(cacheKey, data);
  return data;
}

export async function getFilteredCampaigns(filters: {
  type?: string;
  source?: string;
}): Promise<CampaignItem[]> {
  let list = await getCampaigns();

  if (filters.type) {
    const t = filters.type.toUpperCase();
    list = list.filter((c) => c.typeTag === t);
  }
  if (filters.source) {
    const s = filters.source.toLowerCase();
    list = list.filter((c) => c.source === s);
  }

  return list;
}

/** Bugün (UTC) eklenen / duyurulan ve skoru yüksek kayıtlar */
export async function getTrendingCampaigns(): Promise<CampaignItem[]> {
  const list = await getCampaigns();
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 1);

  const today = (iso?: string) => {
    if (!iso) return false;
    const d = new Date(iso);
    return d >= start && d < end;
  };

  return list
    .filter(
      (c) =>
        (today(c.publishedAt) || today(c.startTime) || today(c.dateAdded)) &&
        c.importanceScore >= 35
    )
    .sort((a, b) => b.importanceScore - a.importanceScore);
}
