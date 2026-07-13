# 05 · Flusso RAG · LOG · Agente (sequenza RCA runtime)

Sequenza di un'analisi RCA lanciata dalla pagina `krateo-health.html`. L'Agent-Core unisce **evidenza** (log reali dei pod) e **conoscenza** (contesto RAG per progetto), poi chiede all'LLM un report strutturato.

```
USER (krateo-health.html)   NGINX :8080      AGENT-CORE :8000       PGVECTOR/PG        K8s API        OLLAMA
        |                       |                   |                    |                |             |
   select ns + click 🧠 ------->|                   |                    |                |             |
        |            POST /api/agent/k8s/analyze --->|                    |                |             |
        |                       |                   | 1. dump describe+events+log -------->|             |
        |                       |                   |<------------------------------------|             |
        |                       |                   | 2. embed query ------------------------------------>|
        |                       |                   |<---------------------------------------------- emb  |
        |                       |                   | 3. retrieval  <=> by project_id --->|                |
        |                       |                   |<-----------------------------------|                |
        |                       |                   | 4. build prompt (LOG + KB) ------------------------->|
        |                       |                   |<------------------------------------- RCA report ---|
        |<------ report MD ------|<-----------------| 5. Stato pod / Problemi / RCA / Azioni correttive    |
```

## Fasi

1. **Raccolta evidenza** — l'Agent-Core interroga la Kubernetes API (RBAC `pods`, `pods/log`, `events`) e fa il bundle di describe + eventi + log dei pod del progetto.
2. **Embedding della query** — la richiesta viene vettorizzata via Ollama (`nomic-embed-text`, dim 768).
3. **Retrieval RAG** — ricerca vettoriale (`<=>`) su `documents_embeddings`, filtrata per `project_id`, per estrarre solo il contesto pertinente al progetto.
4. **Prompt building** — log reali + contesto KB vengono combinati in un prompt strutturato anti-allucinazione.
5. **Report** — l'LLM produce un output Markdown azionabile: **Stato dei Pod**, **Problemi Rilevati**, **Root Cause Analysis** e **Azioni Correttive** (comandi `kubectl` / patch YAML).

## Nota: analisi multi-scopo

Lo stesso motore non è vincolato alla RCA. Cambiando il **prompt di analisi** (a parità di log e RAG) si ottengono lenti diverse sullo stato del cluster: **RCA** per il troubleshooting, ma anche **FinOps** (ottimizzazione costi/risorse), **Security review**, **Compliance** o verifica delle best practice architetturali.

## Nota: ingestione della Knowledge Base

Il retrieval funziona solo se la KB è popolata. L'ingestione avviene via `POST /api/agent/projects/{id}/upload` (dalla pagina `agent.html` o dal pulsante "🧠 Ingesta in RAG" dello scraper): MD → chunk → embedding → `pgvector`, isolati per `project_id`.
</content>
