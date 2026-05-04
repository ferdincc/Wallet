/**
 * News API routes.
 * GET /api/news/latest       → tüm haberler (max 50)
 * GET /api/news/fear-greed   → Fear & Greed Index
 * GET /api/news?source=reddit → kaynak filtresi
 */

import { Router, Request, Response } from 'express';
import { getLatestNews, getFearGreed } from '../services/newsService';

const router = Router();

router.get('/latest', async (_req: Request, res: Response) => {
  try {
    const list = await getLatestNews(50);
    res.json({ success: true, count: list.length, items: list });
  } catch (e) {
    console.error('[newsRoutes] /latest', e);
    res.status(500).json({ success: false, error: (e as Error).message });
  }
});

router.get('/fear-greed', async (_req: Request, res: Response) => {
  try {
    const data = await getFearGreed();
    if (!data) return res.status(502).json({ success: false, error: 'Fear & Greed API unavailable' });
    res.json({ success: true, data });
  } catch (e) {
    console.error('[newsRoutes] /fear-greed', e);
    res.status(500).json({ success: false, error: (e as Error).message });
  }
});

router.get('/', async (req: Request, res: Response) => {
  try {
    const source = typeof req.query.source === 'string' ? req.query.source : undefined;
    const coin = typeof req.query.coin === 'string' ? req.query.coin : undefined;
    const list = await getLatestNews(50, source, coin);
    res.json({ success: true, count: list.length, items: list });
  } catch (e) {
    console.error('[newsRoutes] /', e);
    res.status(500).json({ success: false, error: (e as Error).message });
  }
});

export default router;
