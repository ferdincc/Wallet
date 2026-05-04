import path from 'path';
import { config as loadEnv } from 'dotenv';

// cwd bazen proje kökü olabiliyor; anahtarların her zaman node-backend/.env'den okunması için:
loadEnv({ path: path.resolve(__dirname, '../.env') });

import express from 'express';
import backtestRoutes from './routes/backtestRoutes';
import newsRoutes from './routes/newsRoutes';
import campaignRoutes from './routes/campaignRoutes';
import walletRoutes from './routes/walletRoutes';

const app = express();
const port = process.env.PORT || 3010;

app.use(express.json());

app.use((req, res, next) => {
 res.header('Access-Control-Allow-Origin', '[https://wallet-frontend-swqu.onrender.com](https://wallet-frontend-swqu.onrender.com)');
  res.header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }
  return next();
});

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'node-backend' });
});

app.use('/api/backtest', backtestRoutes);
app.use('/api/news', newsRoutes);
app.use('/api/campaigns', campaignRoutes);
app.use('/api/wallet', walletRoutes);

const portNum = Number(port);
const server = app.listen(portNum, () => {
  console.log(`Node backtest backend listening on http://localhost:${portNum}`);
});

server.on('error', (err: NodeJS.ErrnoException) => {
  if (err.code === 'EADDRINUSE') {
    console.error(
      `[server] Port ${portNum} kullanımda (EADDRINUSE). Eski süreci kapatın: Get-NetTCPConnection -LocalPort ${portNum} veya farklı PORT kullanın.`
    );
  } else {
    console.error('[server] listen error:', err.message);
  }
  process.exit(1);
});


