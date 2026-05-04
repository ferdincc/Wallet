import { Router, Request, Response } from 'express';
import {
  analyzeWallet,
  buildLlmContext,
  buildWalletContext,
  isValidEvmAddress,
  WALLET_CHAINS,
  type ChainKey,
} from '../services/walletAnalysisService';

const router = Router();

function parseChain(q: unknown): ChainKey | 'all' {
  const s = String(q || 'all').toLowerCase();
  if (s === 'all') return 'all';
  const hit = WALLET_CHAINS.find((c) => c.key === s);
  return hit ? (hit.key as ChainKey) : 'all';
}

/** POST /api/wallet/analyze { address, chain?: string } */
router.post('/analyze', async (req: Request, res: Response) => {
  try {
    const address = String(req.body?.address || '').trim();
    if (!isValidEvmAddress(address)) {
      return res.status(400).json({ error: 'Geçersiz EVM adresi (0x + 40 hex).' });
    }
    const chain = parseChain(req.body?.chain);
    const rawMin = req.body?.minUsd;
    const minUsd = typeof rawMin === 'number' ? rawMin : Number(rawMin);
    const result = await analyzeWallet(address, chain, {
      minUsd: Number.isFinite(minUsd) ? minUsd : 10,
    });
    return res.json({
      ...result,
      llmContext: buildLlmContext(result),
      walletContext: buildWalletContext(result),
    });
  } catch (e) {
    console.error('[wallet/analyze]', e);
    return res.status(500).json({ error: (e as Error).message || 'analyze failed' });
  }
});

/** GET /api/wallet/llm-context/:address — WalletAgent / Claude */
router.get('/llm-context/:address', async (req: Request, res: Response) => {
  try {
    const address = String(req.params.address || '').trim();
    if (!isValidEvmAddress(address)) {
      return res.status(400).json({ error: 'invalid address' });
    }
    const chain = parseChain(req.query.chain);
    const qMin = req.query.minUsd;
    const qStr = Array.isArray(qMin) ? qMin[0] : qMin;
    const minUsd = Number(qStr);
    const result = await analyzeWallet(address, chain, {
      minUsd: Number.isFinite(minUsd) ? minUsd : 10,
    });
    const text = buildLlmContext(result);
    return res.json({
      context: text,
      summary: result,
      walletContext: buildWalletContext(result),
    });
  } catch (e) {
    console.error('[wallet/llm-context]', e);
    return res.status(500).json({ error: (e as Error).message || 'context failed' });
  }
});

export default router;
