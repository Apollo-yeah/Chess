#!/usr/bin/env node
/** 本地"生产态"：构建 web/dist → 同时起 Tornado API 与 Vite preview（模拟 Nginx 反代） */
import { apiPort, buildWeb, runApi, runVite, supervise, withDevOrigins } from './lib.js';

console.log('[start] building web → web/dist');
const build = buildWeb();

build.on('exit', (code) => {
  if (code !== 0) {
    console.error('[start] 前端构建失败，已中止');
    process.exit(code ?? 1);
  }

  const port = apiPort();
  const api = runApi(withDevOrigins());
  const web = runVite('preview');
  supervise([api, web]);

  console.log('\n  Web:  http://localhost:4173   （托管 web/dist，/api 与 /ws 代理到后端）');
  console.log(`  API:  http://localhost:${port}\n`);
  console.log('  生产部署请使用：npm run docker:up（Nginx 托管静态资源 + 反代 API）\n');
});
