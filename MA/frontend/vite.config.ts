import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const NODE_BACKEND_PORT = process.env.NODE_BACKEND_PORT || '3010'
const nodeTarget = `http://127.0.0.1:${NODE_BACKEND_PORT}`

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
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
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

