
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
  build: {
    // 用 esbuild 压缩（比默认的 terser 快 10~20 倍、省内存）
    minify: 'esbuild',
    // 低配机不生成 sourcemap，省大量内存
    sourcemap: false,
    // 把巨型库拆分，降低单次转译内存峰值
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor':   ['react', 'react-dom', 'react-router-dom'],
          'antd-vendor':    ['antd', 'dayjs'],
          'icons-vendor':   ['@ant-design/icons'],
          'misc-vendor':    ['axios', 'zustand'],
        },
      },
    },
    // 单文件 > 1.5MB 才告警（Antd 本来就大）
    chunkSizeWarningLimit: 1500,
  },
})
