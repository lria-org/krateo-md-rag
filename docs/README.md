# Documentazione — Diagrammi Krateo MD-RAG

Raccolta dei diagrammi ASCII di riferimento per l'architettura, il deploy e il ciclo di vita della piattaforma **Krateo MD-RAG** (Firecrawl + Agent RAG/RCA su Krateo PlatformOps v3).

Ogni file è autoconsistente e pensato per essere incollato come contesto in prompt futuri o consultato durante il troubleshooting.

| # | Diagramma | Cosa mostra |
|---|---|---|
| 01 | [Architettura Software](01-architettura-software.md) | Il Pod a 7 container, routing Nginx, flussi interni verso pgvector, K8s API e Ollama. |
| 02 | [Processo di Deploy](02-processo-deploy.md) | Flusso GitOps `push → CI → GHCR → ArgoCD sync` con i gotcha tipici. |
| 03 | [Infrastruttura](03-infrastruttura.md) | Layout host/cluster: Mac, Ollama, cluster Kind, namespace e servizi esterni (GitHub, GHCR). |
| 04 | [Aggiornamento della Composition](04-aggiornamento-composition.md) | Come una modifica al Blueprint/CompositionDefinition si propaga fino al cluster. |
| 05 | [Flusso RAG · LOG · Agente](05-flusso-rag-log-agente.md) | Sequenza runtime dell'analisi RCA: log reali + retrieval RAG + LLM → report. |

## Legenda rapida

- **KCO** = Krateo Composable Operations (control plane basato su Helm, non Crossplane).
- **Deploy trigger** = `syncEnabled: true` sulla Composition (non un patch diretto sull'Application ArgoCD).
- **Porte**: portale Krateo `30080` · app NodePort `31181` (blueprint default `31180`).
- **Namespace**: control plane `krateo-system` · scaffolding `demo-system` · app `fireworks-app`.
</content>
</invoke>
