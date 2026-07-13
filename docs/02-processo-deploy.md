# 02 · Processo di Deploy (GitOps: push → CI → Argo)

Il ciclo di rilascio è interamente GitOps: si modifica il codice/chart, si fa `git push`, la CI compila le tre immagini su GHCR e ArgoCD riconcilia il chart dal repo verso il cluster.

```
 DEV (Mac)            GITHUB                              KIND: krateo-quickstart
 ---------            ------                              -----------------------
 edit code        repo lria-org/krateo-md-rag
   |  git push main     |
   +------------------> |  GitHub Actions (ci.yml, MATRIX)
                        |     build+push 3 immagini
                        |            |
                        |            v
                        |     GHCR ghcr.io/lria-org/*  :latest
                        |     krateo-md-rag | agent-core | nuq-postgres
                        |            |  (!) rendere i package PUBLIC
                        |            |
 Krateo Composition     |            |
 GithubScaffolding...   |            |
 spec.argocd.app.       |            |
   syncEnabled: true ---+----> ArgoCD Application (ns krateo-system)
                        |            |   source: repo=chart/  rev=main
                        |            |   destination ns: fireworks-app
                        |            v
                        |       ArgoCD reconcile / sync
                        |            |  chart <- git   images <- GHCR
                        |            v
                        |       Pod 7/7 (fireworks-app) -> NodePort 31181
                        |            |
                        |            v
                        |       ./script/port-forward.sh -> localhost:31181
```

## Gotcha ricorrenti

- **`syncEnabled: false` di default** sulla Composition → Argo vede il drift ma non applica finché non lanci il sync (o imposti `syncEnabled: true`).
- **Namespace `fireworks-app` da creare** se manca `CreateNamespace=true` → errore `namespaces "fireworks-app" not found`.
- **`:latest` + `pullPolicy: IfNotPresent` NON ripulla** l'immagine dalla cache Kind → usa `pullPolicy: Always` (o meglio tag immutabili per SHA).
- **Package GHCR privati** → `ImagePullBackOff`: rendi i package Public o copri con `ghcr-secret`.
- **Edit diretto dell'Application ArgoCD** → viene revertito dalla Composition: modifica sempre a monte, nella Composition/Blueprint.
</content>
