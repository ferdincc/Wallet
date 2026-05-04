/**
 * Kampanya API
 * GET /api/campaigns           → tümü (önem skoruna göre)
 * GET /api/campaigns?type=...  → tür (AIRDROP, …)
 * GET /api/campaigns?source=... → galxe | layer3 | coinmarketcap | nitter
 * GET /api/campaigns/trending  → bugün (UTC) + yüksek skor
 */

import { Router, Request, Response } from 'express';
import { getFilteredCampaigns, getTrendingCampaigns } from '../services/campaignService';

const router = Router();

router.get('/trending', async (_req: Request, res: Response) => {
  try {
    const items = await getTrendingCampaigns();
    res.json({ success: true, count: items.length, items });
  } catch (e) {
    console.error('[campaignRoutes] /trending', e);
    res.status(500).json({ success: false, error: (e as Error).message });
  }
});

router.get('/', async (req: Request, res: Response) => {
  try {
    const type = typeof req.query.type === 'string' ? req.query.type : undefined;
    const source = typeof req.query.source === 'string' ? req.query.source : undefined;
    const items = await getFilteredCampaigns({ type, source });
    res.json({ success: true, count: items.length, items });
  } catch (e) {
    console.error('[campaignRoutes] /', e);
    res.status(500).json({ success: false, error: (e as Error).message });
  }
});

export default router;
