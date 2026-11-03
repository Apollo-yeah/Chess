#!/usr/bin/env node
/** 只构建前端 → web/dist（自包含产物，不再写入 app/static/dist） */
import { buildWeb } from './lib.js';

console.log('[build] Building web → web/dist');

const build = buildWeb();
build.on('exit', (code) => {
  console.log(code === 0 ? '[build] Done.' : `[build] Failed (code=${code}).`);
  process.exit(code ?? 1);
});
