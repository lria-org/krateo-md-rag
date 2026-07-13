# app/ — Sorgenti del Pod Krateo MD-RAG (Firecrawl + Agent RAG/RCA)

Questa cartella contiene i **sorgenti applicativi** dello stack: il ponte Firecrawl, il microservizio AI `agent-core`, l'immagine Postgres custom con `pgvector` e gli strumenti di scraping. In produzione il tutto gira come **Pod a 7 container** su Kubernetes, distribuito in GitOps da Krateo/ArgoCD.

> Per l'architettura completa, il setup Krateo e il flusso di deploy vedi il **[README radice](../README.md)** e i **[diagrammi in `docs/`](../docs/README.md)**. Questo file copre solo i sorgenti e lo sviluppo locale via `docker-compose`.

## Struttura

- `Dockerfile` — ponte Firecrawl (container principale, `ghcr.io/lria-org/krateo-md-rag`).
- `agent-core/` — microservizio FastAPI (RAG ingest + retrieval pgvector + log analysis + RCA). Immagine `ghcr.io/lria-org/krateo-agent-core`.
- `nuq-postgres/` — immagine Postgres custom (`nuq-postgres` + `pgvector`), init `020-pgvector.sql`. Immagine `ghcr.io/lria-org/krateo-nuq-postgres`.
- `tools/` — utility di scraping (`crawl_to_md.py`) per esportare interi siti in Markdown.
- `docker-compose.yml` — stack di sviluppo locale (fuori da Kubernetes).
- `nginx.conf` — split del traffico: `/` statico · `/v1/*` → Firecrawl · `/api/agent/*` → agent-core.

## Requisiti

- Docker Desktop (o Docker Engine + Compose v2)
- [Ollama](https://ollama.com) sul Mac per embedding e chat in locale (evita API a pagamento)
- Facoltativo: Python 3 per lo script CLI di scraping

## Sviluppo locale (docker-compose)

```bash
# 1) configura l'ambiente
cp .env.example .env
# genera i due segreti Firecrawl e incollali nel .env:
openssl rand -hex 24   # → BULL_AUTH_KEY
openssl rand -hex 32   # → AUTUMN_SECRET_KEY

# 2) avvia lo stack (immagini prebuilt)
docker compose up -d
docker compose ps
```

L'API Firecrawl risponde su **http://localhost:3002**, l'Agent-Core su **http://localhost:8000** (o via Nginx sotto `/api/agent/*`). Coda RabbitMQ: http://localhost:15672 (guest/guest).

Test rapido scraping:

```bash
curl -X POST http://localhost:3002/v1/scrape \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","formats":["markdown"]}'
```

## Modelli Ollama

L'Agent-Core usa Ollama per **embedding** e **chat**. Il nome del modello di embedding e la sua **dimensione** devono combaciare con `EMBED_DIM` (default `768`).

```bash
ollama pull nomic-embed-text   # embedding, dim 768 (== EMBED_DIM)
ollama pull gemma2:9b          # chat per la RCA (allineato al README radice)
```

Avvia Ollama in modo raggiungibile dai container: `OLLAMA_HOST=0.0.0.0 ollama serve`. Dai container lo raggiungi via `host.docker.internal:11434` (non `localhost`). Senza Ollama né `OPENAI_API_KEY` lo scraping base funziona, ma restano disattive le funzioni AI (RAG, RCA, `/extract`, JSON mode).

## Note di configurazione

- **`POSTGRES_DB` deve restare `postgres`.** Lo schema della coda usa `pg_cron`, installabile solo nel database indicato da `cron.database_name` (fissato a `postgres` nell'immagine). Cambiandolo, l'init del DB fallisce.
- **pgvector**: l'immagine ufficiale `firecrawl/nuq-postgres` **non** include `pgvector` (solo `pg_cron`). L'Agent-Core memorizza gli embedding in colonna `vector`, quindi si usa l'immagine custom `nuq-postgres/` (`FROM nuq-postgres` + `postgresql-17-pgvector`).
- **Isolamento AI**: l'Agent-Core lavora su uno schema Postgres dedicato `agent` (tabelle `projects`, `documents_embeddings`), separato dalle tabelle di Firecrawl.

Comandi utili: `docker compose logs -f api` · `docker compose logs -f agent-core` · `docker compose down` · reset DB: `docker compose down && docker volume rm firecrawl_postgres-data && docker compose up -d`.

## Pagine web (servite da Nginx)

Le tre pagine statiche del chart (in `../chart/static/`) sono servite da Nginx e condividono lo stesso header di navigazione:

- `index.html` — **Scraper** Firecrawl (crawl → Markdown, export cartella/ZIP/MEGA MD + "🧠 Ingesta in RAG").
- `agent.html` — **RAG**: gestione progetti, upload Knowledge Base, health-check per progetto.
- `krateo-health.html` — **Log & Health**: selezione namespace → pod con errori evidenziati → log → 🧠 lancio dell'Agente (Stato pod / Problemi / RCA / Azioni correttive).

## Strumenti (cartella `tools/`)

### `crawl_to_md.py` — scraper CLI

```bash
python3 tools/crawl_to_md.py https://example.com --limit 100 --out ./scrapes
```

Crea `./scrapes/<sito>/` con un `.md` per pagina + `MAP.md`, mostrando l'avanzamento.

## Licenza

Gli strumenti in `tools/` sono tuoi. Firecrawl e le sue immagini restano soggetti alla licenza del [progetto originale](https://github.com/firecrawl/firecrawl).
</content>
