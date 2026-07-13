# 01 · Architettura Software (Pod a 7 container)

Tutti i componenti vivono nello stesso Pod e comunicano via `localhost`, azzerando latenza di rete e complessità DNS interna. Nginx fa da unico ingresso e ripartisce il traffico verso Firecrawl e l'Agent-Core.

```
                         BROWSER  ->  http://localhost:31181
                                        |
+============================ POD (ns: fireworks-app) =======================+
|                                                                            |
|  [2] nginx-frontend :8080   (reverse proxy + pagine statiche)              |
|       |  /             -> index.html | agent.html | krateo-health.html     |
|       |  /v1/*         -> 127.0.0.1:3002   (Firecrawl)                      |
|       |  /api/agent/*  -> 127.0.0.1:8000   (agent-core)                     |
|       v                                v                                   |
|  [1] firecrawl-api :3002          [7] agent-core :8000  (FastAPI/Python)    |
|       |  scraping (harness.js)         |  - RAG ingest (MD -> chunk -> emb) |
|       |  waits RabbitMQ+PG             |  - retrieval (pgvector <=> )       |
|       v                                |  - k8s log analysis + RCA (/analyze)|
|  [3] playwright :3000                  |                                    |
|  [4] redis :6379                       +--> [6] nuq-postgres :5432          |
|  [5] rabbitmq :5672                    |        schema 'agent' + pgvector   |
|  [6] nuq-postgres :5432  <-------------+                                    |
|                                        +--> K8s API  (SA + RBAC:            |
|                                              pods, pods/log, events)        |
+============================================================================+
                                        |
                                        v
                    Ollama @ host.docker.internal:11434
                    embed: nomic-embed-text (dim 768) | chat: gemma2:9b
```

## Note

- **Ingresso unico**: solo `nginx-frontend` è esposto (NodePort `31181`); tutto il resto è raggiungibile solo via `localhost` interno al Pod.
- **agent-core** è il componente aggiunto rispetto al DAY 1: orchestra RAG, analisi log e RCA. Legge il cluster tramite il ServiceAccount del Pod con RBAC di sola lettura su `pods`, `pods/log`, `events`.
- **nuq-postgres** è un'immagine custom (`postgres:17` + `pgvector`), necessaria per la colonna `vector(768)` degli embedding. Lo schema `agent` è isolato dalle tabelle di Firecrawl.
- **Ollama** gira sul Mac host e fornisce embedding e chat senza chiamate ad API a pagamento; il nome del modello di embedding e la sua dimensione devono combaciare con `EMBED_DIM`.
</content>
