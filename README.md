# krateo-md-rag — Manuale Operativo & Architettura (Firecrawl + Agent RAG/RCA su Krateo PlatformOps)

Questa documentazione è la guida completa al progetto **Krateo MD-RAG**: una piattaforma che parte da un motore di **scraping web resiliente** basato su **Firecrawl** e si evolve in un **Agente AI multi-progetto** capace di ingestione di documentazione Markdown in una **Knowledge Base vettoriale (RAG)**, **analisi dei log** dei pod Kubernetes e **Root Cause Analysis (RCA)** assistita da LLM.

L'intero stack gira in un **unico Pod a 7 container** dentro un cluster Kubernetes locale (**Kind**), ed è distribuito in modalità **GitOps** dalla suite **Krateo PlatformOps v3**: una **CompositionDefinition** (gestita dal *core-provider*, basato su Helm) genera repo, pipeline e una **Application ArgoCD** che riconcilia il chart Helm direttamente dal repository Git. Modifichi il codice, fai `git push`, la CI compila le immagini su GHCR e Argo allinea il cluster allo stato desiderato del repo.

> In una riga: **Firecrawl** raccoglie la conoscenza → la **RAG** la indicizza → l'**Agente** confronta i log reali dei pod con quella conoscenza e produce una diagnosi con azioni correttive.

---

## 📑 Indice

- [0. Quick Start](#-0-quick-start)
- [1. Krateo Setup](#️-1-krateo-setup)
- [2. Setup Blueprint](#️-2-setup-blueprint)
- [3. Setup Composition](#-3-setup-composition)
- [4. GitHub & CI/CD](#-4-github--cicd)
- [5. APP — Architettura del Pod a 7 Container](#️-5-app--architettura-del-pod-a-7-container)
- [6. Agent-Core — RAG, Log Analysis & RCA](#-6-agent-core--rag-log-analysis--rca)
- [7. Flusso DevOps (GitOps completo)](#-7-flusso-devops-gitops-completo)
- [8. Evoluzione: dal Report all'Azione (remediation loop)](#-8-evoluzione-dal-report-allazione-remediation-loop)
- [Diagrammi (cartella `docs/`)](#-diagrammi-cartella-docs)
- [TAKE AWAY — Errori comuni del deploy GitOps](#-take-away--errori-comuni-del-deploy-gitops-argo--composition--provider-dai-miei-appunti-giornalieri)

---

## 🗺️ Diagrammi (cartella `docs/`)

I diagrammi ASCII di riferimento sono in [`docs/`](docs/README.md), un file per vista, così da poterli consultare o incollare come contesto in modo indipendente:

| # | Diagramma | Cosa mostra |
|---|---|---|
| 01 | [Architettura Software](docs/01-architettura-software.md) | Pod a 7 container, routing Nginx, flussi verso pgvector/K8s/Ollama. |
| 02 | [Processo di Deploy](docs/02-processo-deploy.md) | GitOps `push → CI → GHCR → ArgoCD sync` + gotcha. |
| 03 | [Infrastruttura](docs/03-infrastruttura.md) | Layout host/cluster, namespace, servizi esterni. |
| 04 | [Aggiornamento Composition](docs/04-aggiornamento-composition.md) | Propagazione di una modifica al Blueprint/CompositionDefinition. |
| 05 | [Flusso RAG · LOG · Agente](docs/05-flusso-rag-log-agente.md) | Sequenza runtime dell'analisi RCA. |

---

## 🚀 0. QUICK START

Questa sezione porta da zero a un ambiente funzionante. Le sezioni successive spiegano in profondità ogni pezzo.

### 0.1 Prerequisiti

| Requisito | Perché serve | Note |
|---|---|---|
| **Docker Desktop** (o daemon compatibile) | Kind gira dentro Docker; il pod ha sidecar pesanti (Chromium/Playwright). | Minimo **4 vCPU / 8 GB RAM**. |
| **Krateo CLI** (`krateo`) | Inizializza il control plane locale (`krateo quickstart`). | Vedi docs.krateo.io. |
| **kubectl** + **helm** | Debug, sync manuale, ispezione risorse. | Il portale Krateo non basta per il debug per-container. |
| **GitHub PAT** (classic) | Push immagini su GHCR + pull dal cluster. | Scope: `repo`, `write:packages`, `read:packages`. |
| **Ollama in locale** | Fornisce **embedding** e **chat** all'Agent-Core senza chiamare API a pagamento. Tiene tutto sul tuo Mac e velocizza la demo. | `OLLAMA_BASE_URL=http://host.docker.internal:11434`. |

**Modelli Ollama da scaricare** (una volta sola):

```bash
ollama pull nomic-embed-text   # embedding, dimensione 768 (deve combaciare con EMBED_DIM)
ollama pull gemma2:9b          # modello di chat per la RCA (puoi usarne uno più leggero/pesante)
```

> ⚠️ Il nome del modello di embedding e la sua **dimensione** devono combaciare con `EMBED_DIM` in `values.yaml` (`nomic-embed-text` = 768). Se cambi modello, cambia anche la dimensione della colonna `vector`.

### 0.2 Bootstrap del cluster e dei provider

```bash
# 1) Control plane locale: cluster Kind + KCO (core-provider, oasgen/KOG) + ArgoCD + Console Krateo
krateo quickstart

# 2) Verifica che i provider nativi Krateo siano installati (li porta il quickstart / marketplace)
helm list -A | grep -E "core-provider|oasgen-provider|git-provider|github-provider|argocd"

# 3) Segreto pull GHCR nel namespace applicativo (dettaglio in §1.3)
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io --docker-username="<UTENTE>" \
  --docker-password="<PAT>" --docker-email="<EMAIL>" -n fireworks-app
```

### 0.3 Installazione della Blueprint e della Composition (dal template Krateo)

Il progetto nasce dalla blueprint **`fireworks-app-skeleton`** e da una blueprint di **scaffolding con composition** (`github-scaffolding-with-composition-page`) del catalogo Krateo. Questa, compilata dal portale, **genera automaticamente**: il repository Git, la pipeline CI/CD e la **Application ArgoCD** che sincronizza il chart.

```bash
# Installa le blueprint dal repo template Krateo (Helm)
helm repo add krateo https://charts.krateo.io
helm repo update

# Blueprint applicativa (skeleton multi-container)
helm install fireworks-app-skeleton krateo/fireworks-app-skeleton -n krateo-system

# Blueprint di scaffolding: crea repo + composition + Application Argo
helm install github-scaffolding-with-composition-page \
  krateo/github-scaffolding-with-composition-page -n krateo-system
```

Dal **portale Krateo** si compila poi il form della composition (nome app, org GitHub, ecc.). Krateo scaffolda il repo `lria-org/krateo-md-rag` e crea l'Application ArgoCD `krateo-md-rag-<hash>` che punta a `chart/` sul branch `main`.

### 0.4 Primo commit

Il repo scaffoldato contiene lo skeleton. Il primo commit reale porta il codice applicativo (Dockerfile Firecrawl, chart, static) sul branch `main`, scatenando la CI:

```bash
git clone https://github.com/lria-org/krateo-md-rag.git
cd krateo-md-rag
# ... aggiungi Dockerfile custom, chart/, app/ ...
git add -A
git commit -m "first commit: Firecrawl skeleton + chart"
git push origin main
```

Da qui il ciclo è sempre lo stesso: **push → CI builda le immagini su GHCR → sync ArgoCD → pod aggiornato** (vedi §7 e la §TAKE AWAY per gli intoppi tipici).

---

## 🛠️ 1. Krateo Setup

**Krateo PlatformOps** è una piattaforma di Internal Developer Platform (IDP) che standardizza la gestione delle risorse cloud e on-prem con un modello **GitOps + Infrastructure as Code**. Dalla **v2** Krateo ha abbandonato Crossplane: il motore di templating è **Helm** e il control plane è **Krateo Composable Operations (KCO)**, un insieme di operatori nativi Krateo. In pratica Krateo permette a un team di esporre "self-service" applicazioni complesse (via Blueprint/Composition) che gli sviluppatori istanziano dal portale senza conoscere i dettagli Kubernetes sottostanti.

Gli attori principali del control plane (Krateo v3):

- **core-provider** (KCO) — operatore che, da una **CompositionDefinition** che referenzia un chart Helm con `values.schema.json`, genera il CRD corrispondente e deploya un `composition-dynamic-controller` che renderizza il chart con l'RBAC più restrittivo possibile. È il cuore del sistema di composizione (al posto di Crossplane).
- **oasgen-provider** (KOG — Krateo Operator Generator) — genera CRD e controller (`Rest Dynamic Controller`) direttamente da spec **OpenAPI** (`RestDefinition`), senza scrivere operatori a mano. È così che nascono i provider verso API esterne (es. GitHub).
- **git-provider / github-provider** — operatori nativi Krateo per gestione repository e scaffolding (clonano template, creano repo, pushano lo skeleton).
- **ArgoCD** — riconciliazione continua GitOps: confronta lo stato del cluster con lo stato desiderato nel repo Git e allinea (sync).
- **Console/Portal Krateo** — interfaccia self-service per istanziare le Composition (form-driven): compilando il form crei un **Composite Resource** del CRD generato dalla CompositionDefinition.

### 1.1 Inizializzazione del Cluster Locale (Kind Engine)

`krateo quickstart` configura un cluster Kubernetes locale basato su **Kind** (Kubernetes in Docker). Assicurarsi che Docker sia avviato con risorse adeguate (min. 4 vCPU, 8 GB RAM per ospitare Playwright/Chromium e i sidecar).

```bash
krateo quickstart
```

Installa automaticamente:

- Un cluster Kind `krateo-quickstart-control-plane`.
- **ArgoCD** (namespace `krateo-system`) per il sync GitOps.
- **KCO** — gli operatori nativi Krateo: `core-provider`, `oasgen-provider` (KOG), `git-provider`, `github-provider`.
- Le CRD e i componenti della Console Krateo (authn, portal, frontend, ingester/presenter degli eventi, finops, snowplow, ecc.).

### 1.2 Provider nativi Krateo (KCO)

In Krateo v3 **non** si installano provider Crossplane. Gli operatori sono componenti Krateo, distribuiti come release Helm dal quickstart/marketplace. Nel cluster li verifichi con `helm list -A`:

| Provider | Versione (esempio dal cluster) | Ruolo |
|---|---|---|
| **`core-provider`** | 1.0.0 | Gestisce le `CompositionDefinition`: da un chart Helm + `values.schema.json` genera il CRD e il `composition-dynamic-controller` che lo renderizza. |
| **`oasgen-provider`** (KOG) | 0.11.1 | Genera CRD + controller da spec OpenAPI (`RestDefinition`). |
| **`git-provider`** | 0.10.1 | Operazioni Git (clone template, push skeleton). |
| **`github-provider`** (+ `github-provider-kog-repo`) | 0.2.2 | Provider verso le API GitHub (creazione repo, secret), generato via KOG. |

> Le risorse Kubernetes native (Deployment, Service, ConfigMap, Secret) dell'app **non** hanno bisogno di un "provider-kubernetes": le applica direttamente **ArgoCD** sincronizzando il chart dal repo. Non esiste alcun `kind: Release` di `helm.crossplane.io` nel cluster.

### 1.3 Segreti di Sicurezza

**PAT GitHub** — da **Settings > Developer Settings > Personal Access Tokens (classic)** con scope `repo`, `write:packages`, `read:packages`.

**Image Pull Secret** — perché i nodi Kind scarichino le immagini da GHCR. Va creato nel **namespace applicativo** (qui `fireworks-app`, vedi §3):

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="<UTENTE_GITHUB>" \
  --docker-password="<PAT>" \
  --docker-email="<EMAIL>" \
  -n fireworks-app
```

**Credenziali GitHub per i provider Krateo** — `git-provider`/`github-provider` hanno bisogno di un secret con il PAT per creare repo e pushare lo skeleton. Il nome/namespace del secret dipende da come la blueprint di scaffolding è configurata (tipicamente in `krateo-system`); si crea da portale o via `kubectl create secret generic`.

> In Krateo v1 qui si creava un `cluster-config-secret` col kubeconfig per il *provider-kubernetes* di Crossplane. In **v3 non serve**: le risorse le applica ArgoCD, non un provider Crossplane.

---

## 🏗️ 2. Setup Blueprint

La **Blueprint** è il modello architetturale riutilizzabile (il "calco") con cui il team istanzia l'applicazione.

### 2.1 Origine

Punto di partenza: la blueprint **`fireworks-app-skeleton`** del catalogo Krateo, pensata per app poli-container (App + Sidecars). La blueprint di **scaffolding** associata genera repo + pipeline + Composition + Application Argo.

```bash
git clone https://github.com/lria-org/krateo-md-rag.git
cd krateo-md-rag
```

### 2.2 Struttura del repo

- `app/` — sorgenti applicativi: `Dockerfile` (ponte Firecrawl), `agent-core/` (microservizio AI), `nuq-postgres/` (immagine Postgres custom con pgvector), `tools/` (utility di scraping).
- `chart/` — pacchetto Helm: `Chart.yaml`, `values.yaml`, `templates/`, e `static/` (le pagine web servite da Nginx).
- `.github/workflows/ci.yml` — pipeline CI che compila e pubblica **le 3 immagini** su GHCR.
- `script/port-forward.sh` — tunnel locale verso il service.

### 2.3 Dockerfile ponte per Firecrawl

Lo skeleton nativo era basato su Nginx Bitnami. È stato riscritto per ereditare il runtime ufficiale di Firecrawl:

```dockerfile
FROM ghcr.io/firecrawl/firecrawl:latest
USER root
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
USER node
```

---

## 🧩 3. Setup Composition

In Krateo v3 la **Composition** è una **`CompositionDefinition`** gestita dal `core-provider` (basata su Helm, non su Crossplane): il portale compila un form → si crea un **Composite Resource** del CRD generato → il `composition-dynamic-controller` renderizza il chart della blueprint. Nel nostro caso la blueprint di scaffolding non installa l'app direttamente: **scaffolda il repo e crea una Application ArgoCD** che diventa la sorgente di verità del deploy.

### 3.1 Il modello GitOps effettivo

Questo è il punto architetturale più importante (e la fonte della maggior parte degli errori di deploy — vedi §TAKE AWAY):

- La composition di scaffolding crea una **Application ArgoCD** `krateo-md-rag-<hash>` (namespace `krateo-system`).
- L'Application punta a: **repoURL** = il tuo repo, **path** = `chart/`, **targetRevision** = `main`.
- La **destination namespace** dell'Application è **`fireworks-app`**: è lì che vengono create tutte le risorse del chart (Deployment, Service, ConfigMap, RBAC).
- La `syncPolicy` è **manuale**: Argo rileva il drift ma **non applica** finché non lanci un sync.

Trigger del sync (equivale al pulsante "Sync" nella UI Argo):

```bash
kubectl -n krateo-system patch application krateo-md-rag-<hash> --type merge \
  -p '{"operation":{"initiatedBy":{"username":"me"},"sync":{"revision":"main"}}}'
```

### 3.2 Riconciliazione

Ogni modifica ai file del chart nel repo, dopo un sync, viene applicata in Server-Side Apply. Se un container sidecar viene rimosso a mano, Argo lo ripristina allo stato desiderato del repo. Le immagini vengono **sempre da GHCR** (non da `kind load`): la CI deve aver pushato le immagini prima che il pod le pulli.

### 3.3 Namespace

- Risorse applicative: namespace **`fireworks-app`** (destination dell'Application Argo).
- Control plane Krateo (KCO) + ArgoCD: namespace `krateo-system`.

> Nota storica: nella prima iterazione l'app era stata avviata con un `helm install` **manuale** (release `firecrawl` in `krateo-demo`). Quella via è stata dismessa a favore del GitOps puro per evitare drift e conflitti di NodePort (vedi §TAKE AWAY).

---

## 🐙 4. GitHub & CI/CD

Governance del codice e distribuzione immagini affidate a GitHub (org `lria-org`, repo `krateo-md-rag`, registry `ghcr.io`).

### 4.1 Impostazioni repository

- **Settings > Actions > General > Workflow permissions** → **Read and write permissions** (per pushare i package su GHCR).
- **Settings > Secrets and variables > Actions** → eventuali secret (la CI usa `GITHUB_TOKEN` nativo).

### 4.2 Le 3 immagini su GHCR

La pipeline compila e pubblica **tre** immagini (non più una sola):

```
ghcr.io/lria-org/krateo-md-rag:latest          # ponte Firecrawl (container principale)
ghcr.io/lria-org/krateo-agent-core:latest      # microservizio AI (RAG + log analysis + RCA)
ghcr.io/lria-org/krateo-nuq-postgres:latest    # Postgres custom = nuq-postgres + pgvector
```

> ⚠️ Al primo build i package su GHCR nascono **Private**. Vanno resi **Public** (o coperti dal `ghcr-secret`), altrimenti i pod vanno in `ImagePullBackOff`. Package settings → Change visibility → Public, e collegali al repo `krateo-md-rag`.

### 4.3 Pipeline CI (`.github/workflows/ci.yml`)

La CI usa una **matrix** per buildare i tre context in parallelo e pushare su GHCR con tag `:latest` ad ogni push su `main`:

```yaml
name: ci
on:
  push:
    branches: [ 'main' ]
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    strategy:
      matrix:
        include:
          - { name: krateo-md-rag,       context: app }
          - { name: krateo-agent-core,   context: app/agent-core }
          - { name: krateo-nuq-postgres, context: app/nuq-postgres }
    steps:
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: "{{defaultContext}}:${{ matrix.context }}"
          platforms: linux/amd64,linux/arm64
          push: true
          tags: "ghcr.io/${{ github.repository_owner }}/${{ matrix.name }}:latest"
```

Ordine: checkout → login GHCR → build multi-arch → push. **Attenzione al tag mobile `:latest`**: con `pullPolicy: IfNotPresent` il nodo non riscarica un'immagine già in cache. Per questo l'Agent-Core usa `pullPolicy: Always` (vedi §TAKE AWAY, errore #5).

---

## ⚙️ 5. APP — Architettura del Pod a 7 Container

L'app adotta una topologia ad **Alta Coesione Locale**: tutti i componenti vivono nello stesso Pod e comunicano via `localhost`, azzerando la latenza di rete e la complessità DNS interna.

> 📊 Schema completo del Pod (routing e flussi interni): [`docs/01-architettura-software.md`](docs/01-architettura-software.md).

### 5.1 I 7 container

| # | Container | Ruolo | Porta | Dettaglio |
|---|---|---|---|---|
| 1 | `firecrawl-api` (main) | Core engine scraping (`harness.js`) | 3002 | Script `until` in Node.js: aspetta che RabbitMQ (5672) e Postgres (5432) siano pronti prima di avviarsi. |
| 2 | `nginx-frontend` | Reverse proxy + web server | 8080 | `/` serve le pagine statiche; `/v1/*` → Firecrawl; `/api/agent/*` → agent-core. |
| 3 | `playwright-service` | Headless Chromium (render JS) | 3000 | |
| 4 | `redis` | Cache / rate-limit / stato code | 6379 | |
| 5 | `rabbitmq` | Message broker AMQP | 5672 | |
| 6 | `nuq-postgres` | DB relazionale **+ vettoriale** | 5432 | Immagine **custom**: `nuq-postgres` + `pgvector`. |
| 7 | **`agent-core`** | **Orchestratore AI** (RAG + Log Analysis + RCA) | 8000 | FastAPI/Python. Legge i pod via ServiceAccount + RBAC. |

### 5.2 Endpoint esposti (via Nginx, NodePort `31181`)

- `GET /` → UI (scraper Firecrawl).
- `POST /v1/scrape`, `POST /v1/crawl` → Firecrawl.
- `/api/agent/*` → Agent-Core (vedi §6).
- Pagine: `/index.html` (scraper), `/agent.html` (RAG multi-progetto), `/krateo-health.html` (health + RCA).

### 5.3 `chart/values.yaml` (estratto chiave)

```yaml
image:
  repository: ghcr.io/lria-org/krateo-md-rag
  pullPolicy: Always
  tag: latest

service:
  type: NodePort
  port: 31181          # evita conflitti con le porte core di Krateo
  nodePort: 31181

sidecars:
  playwright: { image: ghcr.io/firecrawl/playwright-service:latest }
  redis:      { image: redis:7-alpine }
  rabbitmq:   { image: rabbitmq:3.13-management-alpine }
  postgres:   { image: ghcr.io/lria-org/krateo-nuq-postgres:latest }   # custom + pgvector
  agentCore:  { image: ghcr.io/lria-org/krateo-agent-core:latest }

agentCore:
  enabled: true
  port: 8000
  pullPolicy: Always
  env:
    EMBED_PROVIDER: "ollama"
    OLLAMA_BASE_URL: "http://host.docker.internal:11434"
    MODEL_NAME: "gemma2:9b"
    MODEL_EMBEDDING_NAME: "nomic-embed-text"
    EMBED_DIM: "768"
    AGENT_DB_URL: "postgresql://postgres:postgres@localhost:5432/postgres"

rbac:
  create: true          # ClusterRole per leggere pods, pods/log, events
```

### 5.4 `deployment.yaml` — trucchi

- **Sincronizzazione startup**: il container principale attende con un loop `until` che le porte di RabbitMQ e Postgres siano aperte, evitando crash da race all'avvio.
- **Rollout mirato su modifica ConfigMap**: annotazioni `checksum/config-*` (hash di `static/index.html`, `agent.html`, `krateo-health.html`, nginx). Se cambia una pagina, Argo ricrea **solo** i pod, senza toccare cluster/release.
- **Volumi**: le pagine statiche sono iniettate via ConfigMap e montate in Nginx a runtime (niente rebuild dell'immagine per una modifica UI).

### 5.5 Postgres custom con pgvector

L'immagine ufficiale `ghcr.io/firecrawl/nuq-postgres` è `postgres:17` + `pg_cron`, **senza pgvector**. Poiché l'Agent-Core memorizza gli embedding in una colonna `vector`, serve l'estensione. Immagine custom in `app/nuq-postgres/Dockerfile`:

```dockerfile
FROM ghcr.io/firecrawl/nuq-postgres:latest
ARG PG_MAJOR=17
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      postgresql-${PG_MAJOR}-pgvector && rm -rf /var/lib/apt/lists/*
COPY 020-pgvector.sql /docker-entrypoint-initdb.d/020-pgvector.sql
```

### 5.6 ConfigMap HTML/Nginx

`configmap-html.yaml` inietta `index.html`, `agent.html` e `krateo-health.html`. `configmap-nginx.yaml` fa lo split del traffico: `/` (statico), `/v1/*` → `localhost:3002` (Firecrawl), `/api/agent/*` → `localhost:8000` (agent-core, con `client_max_body_size` e `proxy_read_timeout` alti per upload MD e risposte LLM lente).

---

## 🤖 6. Agent-Core — RAG, Log Analysis & RCA

`agent-core` è un microservizio FastAPI con **endpoint separati** (ogni chiamata fa una cosa sola; `/analyze` compone le altre). Provider LLM configurabile a caldo (Ollama di default, OpenAI opzionale).

> 📊 Sequenza runtime dell'analisi RCA (log + retrieval RAG + LLM): [`docs/05-flusso-rag-log-agente.md`](docs/05-flusso-rag-log-agente.md).

### 6.1 Isolamento e KB

- Schema Postgres dedicato `agent` (non tocca le tabelle di Firecrawl).
- `projects` (id, nome, pod associati) e `documents_embeddings` (chunk MD + `vector(768)`), isolati per `project_id`.
- Retrieval per progetto o **globale** su tutta la KB.

### 6.2 Endpoint principali

| Metodo | Path | Cosa fa |
|---|---|---|
| GET | `/api/agent/health` | Liveness. |
| GET/POST | `/api/agent/config` | Legge/aggiorna provider e modelli a caldo. |
| GET/POST | `/api/agent/projects` | Lista / crea progetto (idempotente, get-or-create). |
| POST | `/api/agent/projects/{id}/upload` | Ingestione MD → chunk → embedding → pgvector. |
| POST | `/api/agent/projects/{id}/rag` | Retrieval (solo ricerca vettoriale). |
| GET | `/api/agent/k8s/pods` | Lista pod di uno o più namespace con stato/errori. |
| GET | `/api/agent/k8s/pods/{ns}/{name}/log` | Log di un singolo pod. |
| POST | `/api/agent/k8s/analyze` | 🧠 **RCA**: bundle (describe + eventi + log) + RAG → report LLM. |

### 6.3 Le tre pagine

Tutte e tre condividono lo **stesso header di navigazione** (barra in alto, identica su ogni pagina) con i link diretti a **🔥 Scraper**, **🤖 RAG** e **🩺 Log & Health**; la pagina corrente è evidenziata.

- **`index.html`** (**🔥 Scraper** Firecrawl): crawl di un sito → Markdown, con export cartella/ZIP/MEGA MD **e** pulsante **"🧠 Ingesta in RAG"** che invia il MEGA MD direttamente alla KB dell'Agente.
- **`agent.html`** (**🤖 RAG**): gestione progetti, upload KB, health-check per progetto.
- **`krateo-health.html`** (**🩺 Log & Health**): selezioni il namespace → vedi i pod con gli **errori evidenziati** → click su un pod → **log** → icona **🧠** che lancia l'Agente. L'Agente raccoglie describe + eventi + log reali, li confronta con la RAG e produce **Stato pod / Problemi / RCA / Azioni correttive**.

### 6.4 RBAC per la lettura dei log

L'Agent-Core legge il cluster tramite il ServiceAccount del pod. Il `ClusterRole` concede:

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "events"]
    verbs: ["get", "list", "watch"]
```

### 6.5 Analisi multi-scopo (prompt-driven)

Il motore non è vincolato alla sola RCA. A parità di **log reali** e **contesto RAG**, cambiando il **prompt di analisi** si ottengono lenti diverse sullo stato del cluster: **Root Cause Analysis** per il troubleshooting, ma anche **FinOps** (ottimizzazione costi/risorse), **Security review**, **Compliance** o verifica delle best practice architetturali. Lo stesso agente diventa così una piattaforma di analisi multi-scopo: RAG e log restano invariati, il prompt definisce la "lente".

---

## 🚀 7. Flusso DevOps (GitOps completo)

> 📊 Schemi di riferimento: [`docs/02-processo-deploy.md`](docs/02-processo-deploy.md) (push → CI → Argo) e [`docs/04-aggiornamento-composition.md`](docs/04-aggiornamento-composition.md) (modifica della Composition).

Il ciclo di rilascio quando l'app è gestita da Krateo/Argo:

1. **Modifica** codice/chart in locale (es. una pagina in `chart/static/`, o `agent-core/`).
2. **Commit + push** su `main`.
3. **CI** (GitHub Actions) builda e pusha le **3 immagini** su GHCR. *Aspetta che sia verde.*
4. **Sync ArgoCD** (manuale): `kubectl patch application ... operation sync` (§3.1).
5. Argo riconcilia il chart → **nuovo pod 7/7** in `fireworks-app`.
6. **Accesso** via port-forward.

### 7.1 `script/port-forward.sh`

Aggiornato al deploy GitOps (namespace `fireworks-app`, service scaffoldato da Krateo, porta `31181`):

```bash
PORT=31181
NAMESPACE="fireworks-app"
SERVICE="krateo-md-rag-<hash>-fireworks-app-skeleton"
kubectl port-forward svc/$SERVICE $PORT:$PORT -n $NAMESPACE > /dev/null 2>&1 &
```

Applicazione accessibile su **http://localhost:31181** → `/krateo-health.html` per l'Agente.

### 7.2 Verifiche post-deploy

```bash
kubectl get pods -n fireworks-app                     # atteso 7/7 Running
# pgvector presente nel Postgres custom?
kubectl exec -n fireworks-app deploy/<release> -c nuq-postgres -- \
  psql -U postgres -tc "SELECT extname FROM pg_extension WHERE extname='vector';"
```

---

## 🔁 8. Evoluzione: dal Report all'Azione (remediation loop)

L'analisi non è il capolinea. La sezione **Azioni Correttive** del report è un output strutturato e macchina-leggibile (comandi `kubectl` e patch YAML): può diventare l'input di un ciclo di remediation che **Krateo mette in atto sull'infrastruttura** restando nel modello dichiarativo.

Come si chiude il loop:

1. L'Agente propone la correzione (patch YAML / bump di versione / fix di config), ancorata alla causa radice identificata dalla RAG.
2. La proposta **non** viene applicata a mano sul cluster: viene tradotta in una modifica al repository (`values.yaml`, ConfigMap, manifest). La fonte di verità resta Git.
3. Krateo **ricompone**: il `core-provider` rilegge il Blueprint aggiornato e rigenera la Composition ([`docs/04-aggiornamento-composition.md`](docs/04-aggiornamento-composition.md)).
4. **ArgoCD sincronizza** lo stato desiderato sul cluster, applicando la correzione in modo tracciato e reversibile.
5. L'Agente può **rianalizzare** i log post-intervento e verificare la risoluzione.

> Vantaggio: nessuna azione distruttiva fuori controllo. Ogni remediation passa da Git — versionata, revisionabile (approvazione umana opzionale prima del sync) e reversibile con un rollback. Si può scegliere tra suggerimento assistito (human-in-the-loop) e remediation completamente automatica a seconda della criticità.

---

## 🧭 TAKE AWAY — Errori comuni del deploy GitOps (Argo / Composition / Provider) dai miei appunti giornalieri

Diario degli intoppi reali incontrati, con sintomo → causa → fix. Sono il 90% dei problemi in un deploy sincronizzato Krateo/Argo.

### Composition & ArgoCD

**1. `one or more objects failed to apply, reason: namespaces "<ns>" not found`**
La `destination.namespace` dell'Application (`fireworks-app`) non esiste e non c'è `CreateNamespace=true`. → **Crea il namespace a mano** (`kubectl create namespace fireworks-app`). Non patchare lo spec dell'Application per aggiungere `syncOptions`: è generato dalla blueprint e verrebbe **riscritto**. Per una soluzione GitOps-pura, codifica la creazione del namespace nella composition.

**2. Application `OutOfSync / Missing`, ma non deploya nulla**
`syncPolicy` è **manuale**: Argo vede il drift ma aspetta. → Lancia il sync (`kubectl patch ... operation`), o premi Sync nella UI Argo. Se vuoi automatismo, imposta `syncPolicy.automated` **nella composition**, come ho fatto io per questa POC sfruttando a pieno l'automatismo.

**3. Il pod che gira non è quello di Argo (naming diverso)**
Un `helm install` **manuale** parallelo (release `firecrawl` in `krateo-demo`) convive con lo stack GitOps (`krateo-md-rag-<hash>-...` in `fireworks-app`). → **Una sola sorgente di verità**: `helm uninstall firecrawl -n krateo-demo` e lascia gestire ad Argo con la sync delle policy attiva (vedi sopra -ndr-).

**4. `provided port 31181 is already allocated` (NodePort conflict)**
Due Service chiedono lo stesso NodePort (il release manuale e quello GitOps). Il NodePort è unico a livello di cluster. → Rimuovi il doppione (errore #3) o cambia porta.

**5. Il fix è pushato e la CI è verde, ma il pod non cambia**
Tag mobile `:latest` + `pullPolicy: IfNotPresent`: il nodo Kind tiene in cache la vecchia immagine e non la riscarica; inoltre se il podspec non cambia, Argo non fa rollout. → `pullPolicy: Always` (e/o `kubectl rollout restart`). Meglio ancora: **tag immutabili** per SHA invece di `:latest`.

**6. `ImagePullBackOff` sulle immagini nuove**
I package GHCR nascono **Private** e i nodi Kind non li vedono. → Rendi i package **Public** o assicura che `ghcr-secret` (org-wide) copra `krateo-agent-core` e `krateo-nuq-postgres`, nel namespace giusto (`fireworks-app`).

**7. `fromRepo vs toRepo` dal Krateo Portal**
La gestione dei values nel portale non è molto chiara per una gestione della UI con scelte grafiche che abbassano la comprensione dei valori e la loro gerarchia. Spesso si confondono i valori con stessa KEY ma gruppo diverso. Es. **fromRepo** e **toRepo** hanno i secret entrambi e va fatta attenzione a impostarli correttamente, la dichiarazione del gruppo della chiave è poco leggibile.

**8. Sync fallisce solo dopo aver aggiunto RBAC**
La `ClusterRoleBinding` referenzia un ServiceAccount in `.Release.Namespace`; se quel namespace non esiste, `kubectl auth reconcile` fallisce. → È il sintomo dell'errore #1: crea prima il namespace.

### Provider & immagini

**9. `agent-core` in CrashLoop: `vector type not found in the database`**
`register_vector()` viene chiamato prima che l'estensione esista. → In `init_db()` esegui `CREATE EXTENSION vector` con una connessione **raw** (senza `register_vector`) e solo dopo registra il tipo.

**10. `CREATE EXTENSION vector` fallisce nel pod**
L'immagine `firecrawl/nuq-postgres` **non** contiene pgvector (solo `pg_cron`). → Usa l'immagine custom `krateo-nuq-postgres` (`FROM nuq-postgres` + `postgresql-17-pgvector`).

### RAG / dati / AI-App

**11. Upload MD → 500 `cannot dump lists of mixed types; got: float, int`**
L'embedding di Ollama mescola `int` e `float` (es. uno `0`), e psycopg rifiuta gli array a tipi misti. → Forza tutti i valori a `float` in `llm.embed()`.

**12. Query RAG → 500 `operator does not exist: vector <=> double precision[]`**
Il parametro embedding viene inviato come array Postgres, non come `vector`; l'operatore `<=>` non fa cast impliciti. → Passa il literal `[...]` con cast esplicito `%s::vector`.

**13. Crea progetto → 500 `duplicate key value violates unique constraint`**
Nome progetto già esistente (re-run smoke test o re-ingest dello stesso sito). → `create_project` idempotente con `INSERT ... ON CONFLICT (name) DO UPDATE`.

**14. RAG "in errore" ma Ollama sembra su**
Dentro un pod Kind, `host.docker.internal` **può non risolvere** verso il Mac dove gira Ollama → l'embedding fallisce con connection refused/timeout. → Verifica la raggiungibilità pod→Ollama (o esponi Ollama in modo raggiungibile dal cluster). Guarda i log di `agent-core`, non gli health probe che li seppelliscono.

### Metodo (dal DAY 1)

**15. La documentazione ufficiale Krateo sul networking locale è risultata obsoleta.** La verità è nei manifesti YAML reali e nel `README.md` del repo della composition definition di Krateo.

**16. Il portale Krateo è limitato per il debug** (niente streaming log per-container, niente auto-esposizione porte): tieni sempre a portata `kubectl` (logs, describe, get events) per il troubleshooting.

---

*Ultimo aggiornamento: 2026-07-13 — stack a 7 container (Firecrawl + Agent RAG/RCA), deploy GitOps via ArgoCD nel namespace `fireworks-app`, CI a 3 immagini su GHCR. Diagrammi di riferimento in [`docs/`](docs/README.md).*
