# Firecrawl self-hosted + Live Scraper

Setup self-hosted di [Firecrawl](https://github.com/firecrawl/firecrawl) con immagini
Docker prebuilt (nessun sorgente da compilare), più due strumenti per esportare interi
siti in Markdown.

## Requisiti

- Docker Desktop (o Docker Engine + Compose v2)
- Facoltativo: [Ollama](https://ollama.com) per le funzioni AI in locale
- Facoltativo: Python 3 per lo script da riga di comando

## Installazione

```bash
git clone https://github.com/<tuo-utente>/<tuo-repo>.git
cd <tuo-repo>

# 1) configura l'ambiente
cp .env.example .env
# genera i due segreti e incollali nel .env:
openssl rand -hex 24   # → BULL_AUTH_KEY
openssl rand -hex 32   # → AUTUMN_SECRET_KEY

# 2) avvia (scarica le immagini prebuilt e parte)
docker compose up -d
docker compose ps
```

L'API risponde su **http://localhost:3002**. Test rapido:

```bash
curl -X POST http://localhost:3002/v1/scrape \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","formats":["markdown"]}'
```

Coda RabbitMQ: http://localhost:15672 (guest/guest).

## Note di configurazione

- **`POSTGRES_DB` deve restare `postgres`.** Lo schema della coda usa `pg_cron`, che
  può essere installato solo nel database indicato da `cron.database_name` (fissato a
  `postgres` nell'immagine). Se lo cambi, l'init del DB fallisce e mancano le tabelle.
- **Ollama** gira sul Mac, i container lo raggiungono via `host.docker.internal` (non
  `localhost`). Avvialo con `OLLAMA_HOST=0.0.0.0 ollama serve` e scarica i modelli:
  `ollama pull deepseek-r1:7b && ollama pull nomic-embed-text`. Senza Ollama né
  `OPENAI_API_KEY`, lo scraping base funziona comunque; restano disattive solo le
  funzioni AI (`/extract`, JSON mode).

Comandi utili: `docker compose logs -f api` · `docker compose down` · reset del DB:
`docker compose down && docker volume rm firecrawl_postgres-data && docker compose up -d`.

## Strumenti (cartella `tools/`)

### `firecrawl-scraper.html` — Live Scraper (browser)
Apri il file nel browser. Inserisci un URL, avvia il crawl e segui l'avanzamento in
tempo reale. A crawl finito puoi esportare:

- **💾 Salva cartella** — una cartella col nome del sito, un file `.md` per pagina
  (struttura a specchio degli URL) + `MAP.md` con l'albero e i link (Chrome/Edge).
- **🗜 ZIP** — stesso contenuto in un archivio (tutti i browser).
- **📄 MEGA MD** — un unico `.md` con in testa l'albero del sito e poi tutte le pagine
  in sequenza (`TITLE` / `URL` / `MARKDOWN`).
- **⬇ JSON** — export grezzo.

### `crawl_to_md.py` — versione CLI
```bash
python3 tools/crawl_to_md.py https://example.com --limit 100 --out ./scrapes
```
Crea `./scrapes/<sito>/` con un `.md` per pagina + `MAP.md`, mostrando l'avanzamento.

## Licenza

Gli strumenti in `tools/` sono tuoi. Firecrawl e le sue immagini restano soggetti alla
licenza del [progetto originale](https://github.com/firecrawl/firecrawl).
