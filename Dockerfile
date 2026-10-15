# Citizen's Voice — one container: FastAPI serves the API and the built dashboard.

# 1) Build the dashboard
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2) Run the API
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/web/dist

# Non-root user
RUN useradd --create-home appuser
USER appuser

# DigitalOcean App Platform sets PORT (8080 by default).
EXPOSE 8080
# Apply any new database migrations, then start the server.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
