# 04 · Aggiornamento della Composition

Esistono due livelli di modifica, con propagazione diversa:

- **Modifica dei contenuti applicativi** (file in `chart/`): segue il flusso di deploy standard → vedi [02 · Processo di Deploy](02-processo-deploy.md).
- **Modifica della Composition/Blueprint** (schema, values di scaffolding, `syncEnabled`, struttura del chart della blueprint): il `core-provider` rigenera il CRD e aggiorna l'Application ArgoCD. È il caso descritto qui.

```
 PLATFORM ENGINEER                 KRATEO CONTROL PLANE (ns: krateo-system)             CLUSTER
 -----------------                 ----------------------------------------             -------
 1. edit Blueprint / values
    (chart Helm + values.schema.json)
    o campi del form Composition
        |
        |  bump chart version / git push
        v
 2. CompositionDefinition (CRD)  --watch-->  core-provider (KCO)
        |                                        |  genera/aggiorna CRD
        |                                        v
        |                                 composition-dynamic-controller
        |                                        |  render chart (RBAC minimo)
        v                                        v
 3. Composite Resource (istanza)  <--- Portale Krateo (form-driven values)
        |                                        |
        |                                        v
        |                                 ArgoCD Application (spec aggiornata)
        |                                        |   source: chart/  rev: main
        |                                        |   syncEnabled: true|false
        |                                        v
 4. Sync (manuale o automatico) ----------> risorse riconciliate in fireworks-app
                                                 |
                                                 v
                                            Pod 7/7 -> NodePort 31181
```

## Punti chiave

- **La sorgente di verità è la Composition, non l'Application**: patchare a mano l'`Application` ArgoCD è inutile, il `core-provider` la riallinea allo stato desiderato della Composition. Ogni cambiamento strutturale (namespace, `syncPolicy`, RBAC, NodePort) va codificato a monte.
- **`syncEnabled`**: è il vero interruttore del deploy automatico. Impostarlo `true` nella Composition abilita il sync continuo; lasciarlo `false` richiede sync manuale.
- **Rigenerazione del CRD**: cambiare `values.schema.json` fa rigenerare il CRD al `core-provider`; assicurarsi che i values esistenti restino compatibili con il nuovo schema per evitare Composite Resource invalide.
- **RBAC e namespace**: se la modifica introduce nuovo RBAC o un namespace nuovo, verificare che il namespace esista prima del sync (altrimenti `kubectl auth reconcile` fallisce).
</content>
