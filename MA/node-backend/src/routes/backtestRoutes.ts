import { Router } from 'express';
import { collectBacktestData, runBacktestHandler } from '../controllers/backtestController';

const router = Router();

// POST /api/backtest/collect-data
router.post('/collect-data', collectBacktestData);

// POST /api/backtest/run
router.post('/run', runBacktestHandler);

export default router;

