# 03 · Infrastruttura

Layout complessivo: il Mac host esegue Docker/OrbStack e Ollama; dentro Docker gira il cluster Kind con il control plane Krateo (KCO) e l'app riconciliata da ArgoCD. GitHub e GHCR sono i servizi esterni per codice e immagini.

```
+------------------------------- Mac (host) --------------------------------+
|  Docker Desktop / OrbStack                                                |
|  Ollama :11434  (nomic-embed-text 768 | gemma2:9b)                        |
|                                                                           |
|  +==================== kind cluster: krateo-quickstart ================+  |
|  |                                                                     |  |
|  |  ns krateo-system   -- CONTROL PLANE (KCO, Helm-based, NO Crossplane)|  |
|  |    core-provider | oasgen-provider (KOG) | git-provider             |  |
|  |    github-provider (+ kog-repo) | argocd | portal :30080 | authn    |  |
|  |    secrets: argocd-endpoint | github-repo-creds                     |  |
|  |                                                                     |  |
|  |  ns demo-system     -- RepoConfiguration | PortalBlueprintPage      |  |
|  |                                                                     |  |
|  |  ns fireworks-app   -- APP (riconciliata da ArgoCD)                 |  |
|  |    Deploy: krateo-md-rag-<hash>-fireworks-app-skeleton              |  |
|  |      Pod (7 container)  ->  Service NodePort 31181                  |  |
|  |    ConfigMap html/nginx | ClusterRole log-reader | ServiceAccount  |  |
|  +=====================================================================+  |
+---------------------------------------------------------------------------+
        |                                        |
        v                                        v
   GitHub  lria-org/krateo-md-rag           GHCR  ghcr.io/lria-org/*
   (repo + Actions CI)                      3 immagini :latest (public)
```

## Note

- **Control plane vs app**: il control plane Krateo (KCO + ArgoCD + portale) vive in `krateo-system`; lo scaffolding in `demo-system`; le risorse applicative in `fireworks-app`.
- **Nessun provider-kubernetes Crossplane**: le risorse native (Deployment, Service, ConfigMap, Secret, RBAC) le applica direttamente ArgoCD sincronizzando il chart.
- **Servizi esterni**: GitHub ospita repo e CI; GHCR ospita le tre immagini con tag `:latest` (da rendere pubbliche).
- **Ollama fuori dal cluster**: raggiunto dai pod via `host.docker.internal:11434`; in un cluster Kind questo hostname può non risolvere e va verificato.
</content>
