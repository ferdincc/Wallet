/**
 * News service: RSS feeds, Reddit, Fear & Greed Index.
 * Cache: 15 minutes (node-cache).
 * Sentiment: keyword-based via newsSentimentService.
 */

import Parser from 'rss-parser';
import axios from 'axios';
import NodeCache from 'node-cache';
import { addSentimentToItem } from './newsSentimentService';
import type { SentimentLabel } from './newsSentimentService';

const CACHE_TTL_SEC = 15 * 60; // 15 minutes
const cache = new NodeCache({ stdTTL: CACHE_TTL_SEC });

const RSS_FEEDS = [
  { url: 'https://www.coindesk.com/arc/outboundfeeds/rss/', source: 'CoinDesk' },
  { url: 'https://cryptonews.com/news/feed/', source: 'CryptoNews' },
  { url: 'https://cointelegraph.com/rss', source: 'Cointelegraph' },
];

/** Bazı RSS kaynakları basit/bot User-Agent ile 403 döndürüyor; tarayıcı benzeri istek kullan. */
const RSS_FETCH_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  Accept: 'application/rss+xml, application/xml, text/xml, */*',
  'Accept-Language': 'en-US,en;q=0.9',
};

const REDDIT_URLS = [
  { url: 'https://www.reddit.com/r/Bitcoin/hot.json', subreddit: 'Bitcoin' },
  { url: 'https://www.reddit.com/r/CryptoCurrency/hot.json', subreddit: 'CryptoCurrency' },
];

const FNG_URL = 'https://api.alternative.me/fng/?limit=1';

/** Coin filter: symbol -> search keywords in title/description (lowercase) */
const COIN_KEYWORDS: Record<string, string[]> = {
  BTC: ['btc', 'bitcoin'],
  ETH: ['eth', 'ethereum'],
  BNB: ['bnb', 'binance coin'],
  SOL: ['sol', 'solana'],
  ADA: ['ada', 'cardano'],
  XRP: ['xrp', 'ripple'],
  DOGE: ['doge', 'dogecoin'],
};

function itemMatchesCoin(item: NewsItem, coin: string): boolean {
  const keywords = COIN_KEYWORDS[coin.toUpperCase()];
  if (!keywords || keywords.length === 0) return false;
  const text = `${item.title || ''} ${item.description || ''}`.toLowerCase();
  return keywords.some((k) => text.includes(k));
}

export interface NewsItem {
  title: string;
  description?: string;
  url: string;
  source: string;
  publishedAt: string; // ISO
  imageUrl?: string;
  score?: number;
  subreddit?: string;
  sentiment?: SentimentLabel;
  sentimentScore?: number;
  matchedWords?: string[];
}

export interface FearGreedResult {
  value: number;
  value_classification: string;
  timestamp: string;
}

const parser = new Parser();

function parseRssItem(item: Parser.Item, source: string): NewsItem {
  const imageUrl =
    (item as any).enclosure?.url ||
    (item as any).content?.match?.(/src="([^"]+)"/)?.[1] ||
    undefined;
  return {
    title: item.title || '',
    description: item.contentSnippet || item.content?.replace(/<[^>]+>/g, '').slice(0, 500) || undefined,
    url: item.link || '',
    source,
    publishedAt: item.pubDate ? new Date(item.pubDate).toISOString() : new Date().toISOString(),
    imageUrl: imageUrl || undefined,
  };
}

/**
 * RSS XML'i axios ile çek (header kontrolü), sonra rss-parser ile parse et.
 * parseURL() doğrudan istek attığı için bazı siteler 403/boş dönüyordu.
 */
async function fetchRssXml(url: string): Promise<string> {
  const { data, status } = await axios.get<string>(url, {
    timeout: 15000,
    headers: RSS_FETCH_HEADERS,
    responseType: 'text',
    maxRedirects: 5,
    validateStatus: (s) => s >= 200 && s < 400,
  });
  if (status !== 200) {
    throw new Error(`HTTP ${status}`);
  }
  const xml = typeof data === 'string' ? data : String(data);
  if (!xml || xml.length < 50) {
    throw new Error('Empty or too short response');
  }
  return xml;
}

async function fetchRssFeeds(): Promise<NewsItem[]> {
  const out: NewsItem[] = [];
  for (const feed of RSS_FEEDS) {
    try {
      const xml = await fetchRssXml(feed.url);
      const parsed = await parser.parseString(xml);
      const items = parsed.items || [];
      console.log(`[newsService] RSS ok ${feed.source}: ${items.length} haber`);
      for (const item of items) {
        out.push(parseRssItem(item, feed.source));
      }
    } catch (e) {
      console.warn(`[newsService] RSS failed ${feed.source}:`, (e as Error).message);
    }
  }
  return out;
}

async function fetchReddit(): Promise<NewsItem[]> {
  const out: NewsItem[] = [];
  for (const { url, subreddit } of REDDIT_URLS) {
    try {
      const { data } = await axios.get(url, {
        timeout: 10000,
        headers: { 'User-Agent': 'OKYISS-News/1.0' },
      });
      const children = data?.data?.children || [];
      for (const c of children) {
        const d = c?.data;
        if (!d?.title) continue;
        out.push({
          title: d.title,
          url: d.url || `https://reddit.com${d.permalink || ''}`,
          source: 'Reddit',
          publishedAt: d.created_utc ? new Date(d.created_utc * 1000).toISOString() : new Date().toISOString(),
          score: d.score,
          subreddit,
        });
      }
    } catch (e) {
      console.warn(`[newsService] Reddit failed r/${subreddit}:`, (e as Error).message);
    }
  }
  return out;
}

async function fetchFearGreed(): Promise<FearGreedResult | null> {
  try {
    const { data } = await axios.get(FNG_URL, { timeout: 8000 });
    const d = data?.data?.[0];
    if (!d) return null;
    return {
      value: Number(d.value) || 0,
      value_classification: d.value_classification || '',
      timestamp: d.timestamp ? new Date(Number(d.timestamp) * 1000).toISOString() : new Date().toISOString(),
    };
  } catch (e) {
    console.warn('[newsService] Fear & Greed failed:', (e as Error).message);
    return null;
  }
}

async function fetchAllNews(): Promise<NewsItem[]> {
  const [rss, reddit] = await Promise.all([fetchRssFeeds(), fetchReddit()]);
  const combined = [...rss, ...reddit].sort(
    (a, b) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()
  );
  return combined.map((item) => addSentimentToItem(item) as NewsItem);
}

export async function getLatestNews(maxItems: number = 50, source?: string, coin?: string): Promise<NewsItem[]> {
  const cacheKey = `news:latest:${source || 'all'}`;
  const cached = cache.get<NewsItem[]>(cacheKey);
  let list: NewsItem[];
  if (cached) {
    list = cached;
  } else {
    const all = await fetchAllNews();
    cache.set('news:latest:all', all);
    list = all;
  }

  if (source) {
    const s = source.toLowerCase();
    list = list.filter((n) => n.source.toLowerCase().includes(s) || n.subreddit?.toLowerCase().includes(s));
  }
  if (coin && COIN_KEYWORDS[coin.toUpperCase()]) {
    list = list.filter((n) => itemMatchesCoin(n, coin));
  }
  return list.slice(0, maxItems);
}

export async function getFearGreed(): Promise<FearGreedResult | null> {
  const cacheKey = 'news:fear-greed';
  const cached = cache.get<FearGreedResult>(cacheKey);
  if (cached) return cached;

  const result = await fetchFearGreed();
  if (result) cache.set(cacheKey, result);
  return result;
}
