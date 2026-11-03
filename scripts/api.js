#!/usr/bin/env node
/** 只启动 Tornado API（前端交给 Vite dev / preview 或 Nginx） */
import { apiPort, pythonBin, runApi } from './lib.js';

const port = apiPort();
console.log(`[api] python: ${pythonBin()}`);
console.log(`[api] http://localhost:${port}\n`);

const api = runApi();
api.on('exit', (code) => process.exit(code ?? 0));
