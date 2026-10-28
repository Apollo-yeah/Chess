# syntax=docker/dockerfile:1
#
# z_chess — 双服务镜像（前端 Nginx + 后端 Tornado API）
#
#   target=web-build  仅构建前端产物 web/dist（不进入最终镜像）
#   target=web        nginx:alpine 提供静态前端并反代 /api、/ws 到 api 服务
#   target=api        python:3.11-slim 运行 Tornado（纯 API + WebSocket，不再托管前端）
#
# 构建：
#   docker build --target web -t z-chess-web .
#   docker build --target api -t z-chess-api .

# ---------------------------------------------------------------------------
# Stage 1: web-build — 前端构建（产物：/app/web/dist）
# ---------------------------------------------------------------------------
FROM node:20-alpine AS web-build

WORKDIR /app

# 依赖清单单独成层，源码变更时不会重复安装依赖
COPY package.json package-lock.json ./

# 锁定版本安装。package-lock.json 已包含 linux/musl 平台的 optional 依赖。
# 注意：echarts-for-react 的 ESM 入口直接 import "tslib" 却未声明该依赖，
# 因此 tslib 已显式加入 package.json 的 dependencies，否则纯净环境构建会
# 报 “Rollup failed to resolve import tslib”。
RUN npm ci --no-audit --no-fund

# scripts/ 必须进镜像：npm run build → node scripts/build.js → npx vite build
COPY scripts ./scripts
# web/ 内含 index.html、vite.config.js、src/、public/
COPY web ./web

# 产出 web/dist（index.html + assets/），自包含、与后端解耦
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2: web — Nginx 静态站点 + API/WebSocket 反向代理
# ---------------------------------------------------------------------------
FROM nginx:alpine AS web

# 独立的 server 级配置，直接作为 conf.d/default.conf 使用（无 http{} 包裹）
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

# 前端产物来自构建阶段，镜像内不携带任何源码
COPY --from=web-build /app/web/dist /usr/share/nginx/html

EXPOSE 80


# ---------------------------------------------------------------------------
# Stage 3: api — Tornado API + WebSocket（无前端静态文件）
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS api

ENV DEBIAN_FRONTEND=noninteractive

# 发行版自带 Stockfish（Debian 安装到 /usr/games/stockfish）。
# 仓库内 app/stockfish/ 是 macOS arm64 二进制，Linux 镜像中不可用，故不复制。
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 仅复制 Python 包源码（.dockerignore 已排除 stockfish 二进制、数据目录、缓存）
COPY app ./app

# /usr/games 通常不在 slim 镜像的 PATH 中，显式加入以便 command -v stockfish 可用
ENV PYTHONPATH=/app \
    STOCKFISH_PATH=/usr/games/stockfish \
    PATH="/usr/games:${PATH}"

EXPOSE 8156

CMD ["python", "-m", "app"]
