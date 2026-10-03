# Stage 1: Build frontend
FROM node:20-alpine AS web
WORKDIR /app
COPY package.json ./
COPY web ./web
RUN npm install
RUN npm run build

# Stage 2: Python runtime
FROM python:3.10-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=web /app/app/static/dist ./app/static/dist

ENV PYTHONPATH=/app
EXPOSE 8156

CMD ["python", "-m", "app"]
