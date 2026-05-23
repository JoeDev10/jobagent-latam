FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema para Playwright / Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium + dependencias del sistema (lo hace playwright mismo)
RUN playwright install --with-deps chromium

# Copiar código fuente
COPY . .

# Directorio de datos en runtime (en free tier no persiste, en paid tier se monta un disco)
RUN mkdir -p /app/data

ENV DATA_DIR=/app/data
ENV PORT=10000

EXPOSE 10000

CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-10000} --log-level info"]
