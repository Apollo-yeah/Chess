#!/usr/bin/env node
/** 开发模式：Tornado API + Vite dev server（Vite 反向代理 /api 与 /ws） */
import { apiPort, pythonBin, runApi, runVite, supervise, withDevOrigins } from './lib.js';

const port = apiPort();

const api = runApi(withDevOrigins());
const web = runVite('dev');

supervise([api, web]);

console.log('\n  Web (dev):  http://localhost:5173');
console.log(`  API:        http://localhost:${port}   (python: ${pythonBin()})`);
console.log('  改动前端 → HMR 即时生效，无需重新构建、无需重启后端\n');
