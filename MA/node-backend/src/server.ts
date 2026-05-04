import path from 'path';
import { config as loadEnv } from 'dotenv';
import express from 'express';
import backtestRoutes from './routes/backtestRoutes';
import newsRoutes from './routes/newsRoutes';
import campaignRoutes from './routes/campaignRoutes';
import walletRoutes from './routes/walletRoutes';

// .env dosyasını yükle
loadEnv({ path: path.resolve(__dirname, '../../.env') });

const app = express();
const port = process.env.PORT || 3010;

app.use(express.json());

// Gelişmiş CORS Ayarı
app.use((req, res, next) => {
  const allowedOrigins = [
    'https://wallet-frontend-swqu.onrender.com', 
    'http://localhost:5173' // Yerelde test edebilmen için eklendi
  ];
  const origin = req.headers.origin;
  
  if (allowedOrigins.includes(origin as string)) {
    res.header('Access-Control-Allow-Origin', origin);
  }
  
  res.header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.header('Access-Control-Allow-Credentials', 'true');

  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }
  next();
});

// Sağlık kontrolü
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'node-backend' });
});

// Route tanımlamaları
app.use('/api/backtest', backtestRoutes);
app.use('/api/news', newsRoutes);
app.use('/api/campaigns', campaignRoutes);
app.use('/api/wallet', walletRoutes);

const portNum = Number(port);
const server = app.listen(portNum, () => {
  console.log(`Server is running on port ${portNum}`);
});

server.on('error', (err: NodeJS.ErrnoException) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`[server] Port ${portNum} kullanımda.`);
  } else {
    console.error('[server] listen error:', err.message);
  }
  process.exit(1);
});
