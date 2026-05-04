import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const NODE_BACKEND_PORT = process.env.NODE_BACKEND_PORT || '3010'
const nodeTarget = 'https://wallet-lsk0.onrender.com'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api/campaigns': {
        target: nodeTarget,
        changeOrigin: true,
      },
      '/api/backtest': {
        target: nodeTarget,
        changeOrigin: true,
      },
      '/api/news': {
        target: nodeTarget,
        changeOrigin: true,
      },
      '/api/wallet': {
        target: nodeTarget,
        changeOrigin: true,
      },
      '/api': {
        target: 'https://wallet-lsk0.onrender.com',
        changeOrigin: true,
      },
      '/ws': {
        target: 'wss://wallet-lsk0.onrender.com',
        ws: true,
      },
      '/node-backend': {
        target: nodeTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/node-backend/, ''),
      },
    },
  },
})
