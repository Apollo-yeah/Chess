import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** 后端地址：dev / preview 下由 Vite 反向代理到 Tornado，生产由 Nginx 承担同样职责 */
const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:8156';
const WS_TARGET = API_TARGET.replace(/^http/, 'ws');

const proxy = {
  '/api': { target: API_TARGET, changeOrigin: true },
  '/ws': { target: WS_TARGET, ws: true, changeOrigin: true },
};

export default defineConfig({
  root: __dirname,
  publicDir: path.resolve(__dirname, 'public'),
  plugins: [react()],
  build: {
    // 前端产物自带于 web/dist：不再混入 app/static/dist，构建与后端彻底解耦
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          echarts: ['echarts', 'echarts-for-react'],
          chessjs: ['chess.js'],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy,
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy,
  },
});
