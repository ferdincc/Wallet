/**
 * Sentiment analysis for news (keyword-based, title + description).
 * Returns: sentiment, sentimentScore (-1..1), matchedWords.
 */

const POSITIVE_WORDS = new Set([
  'bull',
  'bullish',
  'surge',
  'rally',
  'gain',
  'rise',
  'adoption',
  'record',
  'high',
  'pump',
  'growth',
  'soar',
  'breakthrough',
  'partnership',
  'launch',
  'upgrade',
  'institutional',
  'approve',
  'approval',
  'accumulate',
  'buy',
  'support',
  'recover',
  'rebound',
  'milestone',
  'invest',
  'positive',
  'strong',
  'boost',
]);

const NEGATIVE_WORDS = new Set([
  'bear',
  'bearish',
  'crash',
  'drop',
  'fall',
  'ban',
  'hack',
  'lose',
  'low',
  'dump',
  'decline',
  'plunge',
  'fear',
  'risk',
  'scam',
  'fraud',
  'lawsuit',
  'sell',
  'warning',
  'investigation',
  'restrict',
  'block',
  'attack',
  'vulnerability',
  'fine',
  'penalty',
  'collapse',
  'bankrupt',
  'delist',
  'negative',
  'weak',
  'concern',
]);

export type SentimentLabel = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE';

export interface SentimentResult {
  sentiment: SentimentLabel;
  sentimentScore: number;
  /** Eşleşen anahtar kelimeler (pozitifler önce, sonra negatifler; tekrarsız) */
  matchedWords: string[];
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Başlık + açıklama birlikte analiz edilir.
 * Her kelime eşleşmesi ±0.1; skor [-1, 1] aralığına sıkıştırılır.
 * POSITIVE: skor > 0.15 | NEGATIVE: skor < -0.15 | aksi NEUTRAL.
 */
export function analyzeSentiment(text: string): SentimentResult {
  if (!text || typeof text !== 'string') {
    return { sentiment: 'NEUTRAL', sentimentScore: 0, matchedWords: [] };
  }

  const lower = text.toLowerCase();
  let score = 0;
  const matchedPositive: string[] = [];
  const matchedNegative: string[] = [];

  for (const w of POSITIVE_WORDS) {
    const re = new RegExp(`\\b${escapeRegExp(w)}\\b`, 'gi');
    const matches = lower.match(re);
    if (matches && matches.length > 0) {
      score += 0.1 * matches.length;
      matchedPositive.push(w);
    }
  }

  for (const w of NEGATIVE_WORDS) {
    const re = new RegExp(`\\b${escapeRegExp(w)}\\b`, 'gi');
    const matches = lower.match(re);
    if (matches && matches.length > 0) {
      score -= 0.1 * matches.length;
      matchedNegative.push(w);
    }
  }

  score = Math.max(-1, Math.min(1, Math.round(score * 10) / 10));

  let sentiment: SentimentLabel = 'NEUTRAL';
  if (score < -0.15) sentiment = 'NEGATIVE';
  else if (score > 0.15) sentiment = 'POSITIVE';

  const matchedWords = [...matchedPositive, ...matchedNegative];

  return { sentiment, sentimentScore: score, matchedWords };
}

/**
 * Add sentiment to a news item (title + optional description).
 */
export function addSentimentToItem<T extends { title: string; description?: string }>(item: T): T & SentimentResult {
  const text = [item.title, item.description].filter(Boolean).join(' ');
  return { ...item, ...analyzeSentiment(text) };
}
