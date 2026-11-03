#!/usr/bin/env node
/** 三个脚本共用的进程编排工具（无第三方依赖） */
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function pythonBin() {
  if (process.env.PYTHON) return process.env.PYTHON;
  return process.platform === 'win32' ? 'python' : 'python3';
}

export function apiPort() {
  return process.env.PORT || '8156';
}

export function webPort(kind) {
  return kind === 'dev' ? '5173' : '4173';
}

/**
 * 开发/预览时前端与 API 端口不同，浏览器发出的 Origin 与 API 的 Host 不一致，
 * 因此要把前端来源显式加入 API 的 CORS/WebSocket 白名单。
 * 生产环境走 Nginx 同源反代，无需任何白名单（默认即为空）。
 */
export function withDevOrigins(env = {}) {
  if (process.env.CHESS_CORS_ORIGINS) return env;
  const origins = ['5173', '4173'].flatMap((port) => [
    `http://localhost:${port}`,
    `http://127.0.0.1:${port}`,
  ]);
  return { ...env, CHESS_CORS_ORIGINS: origins.join(',') };
}

export function run(cmd, args, opts = {}) {
  return spawn(cmd, args, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...opts,
  });
}

/** 启动 Tornado API（PYTHONPATH 指向仓库根，保证 app 包可导入） */
export function runApi(extraEnv = {}) {
  return run(pythonBin(), ['-m', 'app'], {
    cwd: root,
    env: { ...process.env, PYTHONPATH: root, ...extraEnv },
  });
}

/** 启动 Vite（dev 或 preview） */
export function runVite(mode) {
  const args =
    mode === 'preview'
      ? ['vite', 'preview', '--config', 'web/vite.config.js']
      : ['vite', '--config', 'web/vite.config.js'];
  return run('npx', args, { cwd: root });
}

export function buildWeb() {
  return run('npx', ['vite', 'build', '--config', 'web/vite.config.js'], { cwd: root });
}

/** 任一子进程异常退出或收到信号时，统一清理全部子进程 */
export function supervise(children) {
  let closing = false;
  const shutdown = (code = 0) => {
    if (closing) return;
    closing = true;
    for (const child of children) {
      try {
        child.kill('SIGTERM');
      } catch {
        /* 已退出 */
      }
    }
    setTimeout(() => process.exit(code), 150);
  };

  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));
  for (const child of children) {
    child.on('exit', (code) => {
      if (!closing && code !== 0 && code !== null) {
        console.error(`\n[dev] 子进程退出（code=${code}），正在停止其余进程`);
        shutdown(code);
      }
    });
  }
  return shutdown;
}
