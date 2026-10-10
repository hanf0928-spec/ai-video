
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    // 监听所有网卡，允许局域网/公网 IP 直连（开发期）
    host: '0.0.0.0',
    port: 5173,
    // 允许任意 Host 头，防止 "Blocked request" 报错（Vite 5+ 的 host check）
    // 生产部署请使用 `npm run build` 产物 + Nginx，不走 dev server
    allowedHosts: 'all' as any,
    proxy: {
      '/api':    { target: 'http://localhost:8000', changeOrigin: true },
      '/static': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws':     { target: 'ws://localhost:8000',   ws: true, changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: 'all' as any,
  },
})
