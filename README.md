# krateo-md-rag (Firecrawl Platform) - Manuale Operativo & Documentazione di Architettura

Questa documentazione fornisce una guida passo-passo e un'analisi architetturale approfondita per il progetto **Krateo MD-RAG**. Il sistema implementa un'infrastruttura di scraping ed estrazione dati altamente resiliente basata sulla piattaforma **Firecrawl**, ottimizzata per l'integrazione con sistemi RAG (Retrieval-Augmented Generation) operanti su documenti Markdown. L'intero stack è orchestrato all'interno di un cluster Kubernetes locale tramite la suite **Krateo Platform Ops**.

---

## 🛠️ 1. KRateo SETUP

La Krateo Platform Ops consente di standardizzare la gestione delle risorse cloud e on-premises sul modello GitOps e Infrastructure as Code (IaC) sfruttando Crossplane sotto il cofano.

### 1.1 Inizializzazione del Cluster Locale (Kind Engine)

Krateo Quickstart configura un cluster Kubernetes locale basato su **Kind** (Kubernetes in Docker). Prima di procedere, assicurarsi che Docker Desktop o un demone Docker compatibile sia avviato e presenti risorse adeguate (minimo 4 vCPU, 8 GB di RAM consigliati per ospitare i sidecar pesanti come Playwright/Chromium).

Eseguire l'inizializzazione dell'ambiente di controllo:

```bash
krateo quickstart
```

Questo comando automatizza l'installazione di:

- Un cluster Kubernetes denominato `krateo-quickstart-control-plane`.
- **ArgoCD**: per la sincronizzazione continua dello stato desiderato dai repository Git.
- **Crossplane**: il motore di aggregazione API che funge da control plane universale.
- Le definizioni delle risorse di base (CRD) per la console utente di Krateo.

### 1.2 Installazione ed Abilitazione degli Operatori (Crossplane Providers)

Per consentire a Krateo di orchestrare sia componenti infrastrutturali che pacchetti applicativi, è necessario installare e configurare i seguenti Core Provider. I manifesti possono essere applicati tramite la console di Krateo o via `kubectl`.

#### A. Provider Kubernetes

Consente a Crossplane di interagire con le API interne del cluster per creare oggetti nativi come `Deployment`, `Service`, `ConfigMap` e `Secret`.

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
spec:
  package: xpkg.upbound.io/crossplane/provider-kubernetes:v0.9.0
```

#### B. Provider Helm

Indispensabile per il deployment dei grafici Helm (HelmReleases) definiti dalle nostre composizioni e blueprint.

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-helm
spec:
  package: xpkg.upbound.io/crossplane/provider-helm:v0.11.0
```

#### C. Provider GitHub

Utilizzato se si desidera automatizzare la creazione di repository o segreti dell'organizzazione direttamente dal control plane.

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-github
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-github:v0.1.0
```

### 1.3 Configurazione e Generazione dei Segreti di Sicurezza

L'applicazione necessita di un canale sicuro per interagire con i registri dei container protetti e con le API esterne. I segreti devono essere collocati nel namespace operativo dell'applicazione, definito come `krateo-demo`.

#### A. Generazione del Personal Access Token (PAT) di GitHub

1. Accedere al proprio account GitHub e navigare su **Settings > Developer Settings > Personal Access Tokens > Tokens (classic)**.
2. Generare un nuovo token impostando i seguenti scope minimi richiesti:
   - `repo` (controllo completo dei repository privati)
   - `write:packages` (caricamento delle immagini Docker su GHCR)
   - `read:packages` (download delle immagini Docker da GHCR)

#### B. Creazione dell'Image Pull Secret in Kubernetes

Per consentire ai nodi del cluster Kind di autenticarsi su GitHub Container Registry (ghcr.io) e scaricare l'immagine applicativa compilata:

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="IL_TUO_UTENTE_GITHUB" \
  --docker-password="IL_TUO_PERSONAL_ACCESS_TOKEN" \
  --docker-email="LA_TUA_EMAIL@esempio.com" \
  -n krateo-demo
```

#### C. Configurazione delle Credenziali dei Provider Crossplane

Per sbloccare il Provider Kubernetes, creare una configurazione di autenticazione che punti al file kubeconfig interno del cluster, permettendo a Crossplane di agire come amministratore:

```bash
kubectl create secret generic cluster-config-secret --from-file=kubeconfig=$HOME/.kube/config -n krateo-system
```

---

## 🏗️ 2. Setup Blueprint

Il Blueprint in Krateo rappresenta il modello architetturale standardizzato (il "calco") riutilizzabile dal team di sviluppo per istanziare l'applicazione.

### 2.1 Download e Clonazione del Blueprint Originario

Il punto di partenza è il blueprint strutturale denominato `fireworks-app-skeleton`, fornito dal catalogo Krateo per la creazione rapida di applicazioni poli-container (App + Sidecars).

```bash
git clone https://github.com/lria-org/krateo-md-rag.git
cd krateo-md-rag
```

### 2.2 Scomposizione e Ispezione della Struttura Modello

Il blueprint scaricato si articola nelle seguenti componenti core:

- `app/` — Contiene gli asset applicativi locali (tra cui il sorgente statico del frontend).
- `chart/` — Contiene la definizione del pacchetto Helm (`Chart.yaml`, `values.yaml` e la cartella `templates/`).
- `.github/workflows/` — Contiene le pipeline pre-configurate per automatizzare la compilazione e il rilascio.

### 2.3 Refactoring del Dockerfile Modello

Il blueprint nativo implementava uno skeleton statico basato su un'immagine Bitnami Nginx. Per abilitare la logica di Firecrawl, il file `Dockerfile` posizionato nella root del progetto è stato interamente riscritto per ereditare l'ambiente runtime ufficiale di Firecrawl:

```dockerfile
FROM ghcr.io/firecrawl/firecrawl:latest

# Eventuali personalizzazioni di script o estensioni locali vanno inserite qui
USER root
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
USER node
```

---

## 🧩 3. Setup Composition

La Composition in Crossplane è l'oggetto logico che traduce una richiesta astratta dell'utente (un Claim) in un insieme concreto di risorse Kubernetes configurate (Deployment, Service, PersistentVolume).

### 3.1 Architettura della Composition per il Chart Helm

La Composition prende l'input utente inviato tramite la Console Krateo e lo mappa direttamente nei parametri interni del Chart Helm di Firecrawl. L'oggetto centrale è un `Release` del provider Helm:

```yaml
apiVersion: helm.crossplane.io/v1beta1
kind: Release
metadata:
  name: firecrawl-application-release
spec:
  forProvider:
    chart:
      repository: https://lria-org.github.io/krateo-md-rag
      name: fireworks-app
      version: 0.1.0
    namespace: krateo-demo
    values:
      replicaCount: 1
      image:
        tag: "latest"
```

### 3.2 Sincronizzazione dello Stato tramite Compositions

Ogni volta che viene effettuata una variazione nei file del Chart, Crossplane intercetta l'evento, esegue un "dry-run" di validazione e applica le modifiche in modalità Server-Side Apply. Se un container sidecar fallisce o viene rimosso manualmente da un amministratore, Crossplane interviene autonomamente per ripristinare i 6 container originari richiesti dalla Composition.

### 3.3 Namespace e Claim

- **Namespace**: le risorse vengono rilasciate nel namespace isolato `krateo-demo`.
- **Claim**: il file YAML di istanziazione applicato dall'utente per scatenare la creazione del cluster applicativo, che innesca la Composition.

---

## 🐙 4. GITHUB

La governance del codice sorgente e la distribuzione dei pacchetti applicativi sono interamente affidate all'ecosistema GitHub dell'organizzazione.

### 4.1 Configurazione dell'Organizzazione e dei Repository

- **Organizzazione target**: `lria-org`
- **Repository**: `krateo-md-rag`
- **Visibilità**: impostata per garantire l'accesso ai moduli del cluster Krateo.

Nelle impostazioni della repository (**Settings > Actions > General**), assicurarsi che sotto *Workflow permissions* sia abilitata l'opzione **Read and write permissions**, indispensabile per consentire alla pipeline di caricare i pacchetti d'immagine compilati sul registro interno.

Sotto **Settings > Secrets and variables > Actions**, impostare eventuali secret necessari (es. `CR_PAT` per il container registry).

### 4.2 GitHub Packages (GHCR)

Tutte le immagini Docker compilate vengono ospitate su GHCR. L'identificativo univoco dell'immagine del microservizio è:

```
ghcr.io/lria-org/krateo-md-rag:latest
```

Quando la pipeline compila l'immagine per la prima volta, il pacchetto su GitHub potrebbe essere contrassegnato come *Private*. È fondamentale navigare sulla pagina del pacchetto (**Package Settings**) e collegarlo esplicitamente alla repository `krateo-md-rag`, garantendo che i permessi di pull siano sincronizzati con il token PAT configurato nel cluster Krateo.

### 4.3 GitHub Actions — Pipeline CI/CD (`build-and-push.yml`)

All'interno di `.github/workflows/build-and-push.yml` è implementata la pipeline di integrazione continua:

```yaml
name: Build and Push Firecrawl Custom Image

on:
  push:
    branches: [ "main" ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and Push Docker Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/lria-org/krateo-md-rag:latest
```

La pipeline esegue, in ordine: checkout del codice, autenticazione su `ghcr.io`, build dell'immagine basata sul Dockerfile custom, e push dell'immagine con tag `latest`.

---

## ⚙️ 5. APP (Architettura e Struttura Helm Chart)

L'applicazione implementa una topologia ad **Alta Coesione Locale** (Pod Multicontainer): tutti i componenti necessari al funzionamento di Firecrawl convivono nello stesso Pod e comunicano tramite l'interfaccia di loopback (`localhost`), garantendo latenze di rete pari a zero e rimuovendo la necessità di configurare complessi DNS interni di Kubernetes.

### 5.1 I 6 Container Co-Locati nel Pod

| Container | Ruolo | Porta interna |
|---|---|---|
| `firecrawl-api` (main) | Orchestrazione dello scraping, esegue `harness.js`. Ciclo Node.js in linea che funge da `depends_on` dinamico, attendendo l'apertura delle porte dei database sidecar prima di avviarsi. | 3002 |
| `nginx-frontend` | Reverse proxy e web server (`nginx:alpine`). Serve i file statici dell'UI e inoltra le chiamate `/v1/*` al container Firecrawl. | 8080 |
| `playwright-service` | Browser headless Chromium per il rendering JS delle pagine complesse. | 3000 |
| `redis` | Cache in-memory, rate-limiter e gestione stato code job. | 6379 |
| `rabbitmq` | Message broker AMQP per la distribuzione dei task tra worker paralleli. | 5672 |
| `nuq-postgres` | Database relazionale per lo storage strutturato dei dati estratti. | 5432 |

### 5.2 Endpoint Esposti

Tramite Nginx (porta interna 8080, esposta come NodePort/ClusterIP a seconda della configurazione), l'app risponde a:

- `GET /` → Interfaccia utente web.
- `POST /v1/scrape` → Endpoint per inviare richieste di conversione URL → Markdown.

### 5.3 File `chart/values.yaml`

Espone l'interfaccia di configurazione globale: credenziali predefinite, disattivazione dei tentativi di Firecrawl di avviare container Docker interni (sostituiti dai sidecar stabili), e tipo di servizio.

```yaml
replicaCount: 1

image:
  repository: ghcr.io/lria-org/krateo-md-rag
  pullPolicy: Always
  tag: latest

service:
  type: ClusterIP
  port: 8181

ingress:
  enabled: false

# Ambiente applicativo unificato per esecuzione locale
env:
  HOST: "0.0.0.0"
  PORT: "3002"
  ENV: "local"
  NUQ_DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/postgres"
  REDIS_URL: "redis://localhost:6379"
  REDIS_RATE_LIMIT_URL: "redis://localhost:6379"
  PLAYWRIGHT_MICROSERVICE_URL: "http://localhost:3000/scrape"
  POSTGRES_HOST: "localhost"
  POSTGRES_PORT: "5432"
  POSTGRES_USER: "postgres"
  POSTGRES_PASSWORD: "postgres"
  POSTGRES_DB: "postgres"
  USE_DB_AUTHENTICATION: "false"
  NUM_WORKERS_PER_QUEUE: "8"
  CRAWL_CONCURRENT_REQUESTS: "10"
  MAX_CONCURRENT_JOBS: "5"
  BROWSER_POOL_SIZE: "5"
  LOGGING_LEVEL: "info"
  BULL_AUTH_KEY: "CHANGEME"
  ALLOW_LOCAL_WEBHOOKS: "false"
  BLOCK_MEDIA: "false"
  EXTRACT_WORKER_PORT: "3004"
  WORKER_PORT: "3005"
  NUQ_RABBITMQ_URL: "amqp://localhost:5672"
  HARNESS_STARTUP_TIMEOUT_MS: "60000"

sidecars:
  playwright:
    image: ghcr.io/firecrawl/playwright-service:latest
  redis:
    image: redis:7-alpine
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
  postgres:
    image: ghcr.io/firecrawl/nuq-postgres:latest
```

### 5.4 File `chart/templates/deployment.yaml`

Il cuore dell'infrastruttura: definisce i 6 container, le readiness probe e monta i volumi delle ConfigMap. Il blocco `command` del container principale implementa un meccanismo di sincronizzazione dinamica via Node.js, per evitare che Firecrawl vada in crash se avviato prima che RabbitMQ e Postgres siano pronti:

```yaml
          command: ["/bin/sh", "-c"]
          args:
            - |
              echo "==> [STARTUP] Controllo disponibilità di RabbitMQ (porta 5672)..."
              until node -e "const net = require('net'); const c = net.connect({port: 5672, host: 'localhost'}, () => process.exit(0)); c.on('error', () => process.exit(1));" 2>/dev/null; do
                echo "==> [STARTUP] RabbitMQ non è ancora pronto. Ricontrollo tra 2 secondi..."
                sleep 2
              done

              echo "==> [STARTUP] Controllo disponibilità di Postgres (porta 5432)..."
              until node -e "const net = require('net'); const c = net.connect({port: 5432, host: 'localhost'}, () => process.exit(0)); c.on('error', () => process.exit(1));" 2>/dev/null; do
                echo "==> [STARTUP] Postgres non è ancora pronto. Ricontrollo tra 2 secondi..."
                sleep 2
              done

              echo "==> [STARTUP] Tutti i servizi backend sono ONLINE! Avvio Firecrawl..."
              node dist/src/harness.js --start-docker
```

Sezione `volumes`, per montare l'interfaccia utente statica a runtime dentro Nginx:

```yaml
          volumeMounts:
            - name: html-files
              mountPath: /usr/share/nginx/html
            - name: nginx-config
              mountPath: /etc/nginx/conf.d
      volumes:
        - name: html-files
          configMap:
            name: {{ include "fireworks-app.fullname" . }}-html
        - name: nginx-config
          configMap:
            name: {{ include "fireworks-app.fullname" . }}-nginx-config
```

### 5.5 File `chart/templates/configmap-html.yaml`

Inietta il contenuto di `static/index.html` direttamente nel filesystem di Kubernetes, rendendolo leggibile da Nginx senza bisogno di ricompilare l'immagine Docker a ogni modifica del frontend:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "fireworks-app.fullname" . }}-html
data:
  index.html: |
{{ .Files.Get "static/index.html" | indent 4 }}
```

### 5.6 File `chart/templates/configmap-nginx.yaml`

Contiene la configurazione di routing `nginx.conf` per lo split del traffico tra Frontend (`/`) e API (`/v1/*`) verso il container Firecrawl.

---

## 🚀 6. Primo Avvio (Flusso DevOps Completo)

### 6.1 Flusso DevOps di Rilascio

1. **Modifica del codice Frontend**: lo sviluppatore modifica il file `app/web/index.html` in locale.
2. **Allineamento statico**: il file viene copiato nella cartella del chart (`chart/static/index.html`).
3. **Rilascio locale**: Helm disinstalla la vecchia release e riapplica i manifesti, aggiornando la ConfigMap sul cluster istantaneamente.
4. **Push su GitHub**: al completamento delle feature, un `git push` attiva la GitHub Action, che compila l'immagine core e aggiorna il tag remoto per l'ambiente gestito da ArgoCD.

### 6.2 Comandi Operativi per il Reset del Rilascio

Per sincronizzare l'HTML aggiornato e forzare un aggiornamento radicale di tutti i componenti del cluster locale:

```bash
# Sincronizza l'HTML aggiornato nella cartella del Chart Helm
mkdir -p chart/static
cp app/web/index.html chart/static/index.html

# Esegue il wipe completo della vecchia istanza applicativa
helm uninstall firecrawl -n krateo-demo

# Installa il pacchetto aggiornato con le nuove configurazioni
helm install firecrawl ./chart -n krateo-demo
```

### 6.3 Automazione del Canale di Rete (`port-forward.sh`)

Per evitare interferenze con le porte core di Krateo (console globale, ArgoCD) ed esporre l'applicazione senza occupare il terminale, è stato sviluppato uno script di automazione per il tunnel.

Creare lo script `port-forward.sh` nella root del progetto:

```bash
#!/bin/bash

PORT=8181
NAMESPACE="krateo-demo"
SERVICE="firecrawl-fireworks-app-skeleton"

echo "🔄 Pulizia: controllo se ci sono vecchi tunnel aperti sulla porta $PORT..."
PID=$(lsof -t -i:$PORT)
if [ ! -z "$PID" ]; then
    echo "💀 Trovato tunnel residuo (PID: $PID). Lo chiudo..."
    kill -9 $PID
    sleep 1
fi

echo "🔌 Attivo il nuovo port-forward in background..."
kubectl port-forward svc/$SERVICE $PORT:$PORT -n $NAMESPACE > /dev/null 2>&1 &

sleep 2

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "========================================================"
    echo "✅ ARCHITETTURA DI RETE ATTIVA!"
    echo "🌐 Accedi al Frontend e alle API su: http://localhost:$PORT"
    echo "========================================================"
else
    echo "❌ Errore: Il tunnel non è partito. Verifica lo stato del Pod."
fi
```

Abilitare i permessi di esecuzione ed avviare lo script:

```bash
chmod +x port-forward.sh
./port-forward.sh
```

Il terminale torna immediatamente disponibile. L'applicazione è accessibile in modo permanente all'indirizzo:

**http://localhost:8181**

Nginx gestisce autonomamente il caricamento dell'interfaccia grafica e la deviazione trasparente delle richieste di scraping verso il core engine di Firecrawl.
