# Étape 1 : construction de l'interface (Svelte + Vite)
FROM node:22-alpine AS front
WORKDIR /front
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Étape 2 : serveur Python
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=front /front/dist ./static/
COPY run.sh /run.sh
RUN chmod +x /run.sh
CMD ["/run.sh"]
