# Imagem única: serve a API Flask e, pela mesma porta, os arquivos
# estáticos do frontend (index.html + assets/), como app.py já faz via
# FRONTEND_DIR. Não há passo de build de frontend — é HTML/CSS/JS puro.

FROM python:3.12-slim

# postgresql-client é necessário porque migrate.py aplica as migrations
# via `psql` (transporte usado tanto no fallback sem driver quanto,
# aqui, como ferramenta de linha de comando para as migrations em si;
# a API em si usa o driver psycopg, instalado via requirements.txt).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Frontend estático (raiz do projeto)
COPY index.html ./index.html
COPY assets ./assets

# Backend
COPY backend ./backend

RUN mkdir -p /app/backend/uploads
VOLUME ["/app/backend/uploads"]

WORKDIR /app/backend
EXPOSE 8000

# Aplica migrations pendentes e, se BOOTSTRAP_ADMIN_EMAIL/PASSWORD
# estiverem definidos, garante o admin inicial, antes de subir a API.
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", "--timeout", "60", "app:app"]
