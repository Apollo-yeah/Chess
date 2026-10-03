#!/usr/bin/env node
import { execSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

console.log('[build] Building web → app/static/dist');

execSync('npx vite build --config web/vite.config.js', {
  cwd: root,
  stdio: 'inherit',
});

console.log('[build] Done.');
