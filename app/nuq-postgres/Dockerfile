# Postgres di Firecrawl (nuq-postgres = postgres:17 + pg_cron) ESTESO con pgvector.
# Serve ad agent-core: senza l'estensione 'vector', CREATE EXTENSION vector fallisce.
# Base gia' contiene lo schema nuq (nuq.sql in /docker-entrypoint-initdb.d).
FROM ghcr.io/firecrawl/nuq-postgres:latest

ARG PG_MAJOR=17
USER root

# Installa l'estensione pgvector dal repo PGDG (gia' configurato nell'immagine postgres ufficiale)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-${PG_MAJOR}-pgvector; \
    rm -rf /var/lib/apt/lists/*

# init.d: crea l'estensione al primo bootstrap (agent-core la richiede comunque a runtime)
COPY 020-pgvector.sql /docker-entrypoint-initdb.d/020-pgvector.sql
