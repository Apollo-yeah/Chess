#!/usr/bin/env node
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

function run(cmd, args, opts = {}) {
  return spawn(cmd, args, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...opts,
  });
}

const python = run('python', ['-m', 'app'], {
  cwd: root,
  env: { ...process.env, PYTHONPATH: root },
});

const vite = run('npx', ['vite', '--config', 'web/vite.config.js'], {
  cwd: root,
});

function shutdown() {
  python.kill();
  vite.kill();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

python.on('exit', (code) => {
  if (code !== 0 && code !== null) shutdown();
});
vite.on('exit', (code) => {
  if (code !== 0 && code !== null) shutdown();
});

console.log('\n  Dev server: http://localhost:5173');
console.log('  API server: http://localhost:8156\n');
