"""Accesso Kubernetes via API ufficiale. Usa il ServiceAccount montato nel pod (in-cluster),
con fallback al kubeconfig locale in dev. RBAC: pods + pods/log (vedi agent-rbac.yaml)."""
from kubernetes import client, config as kconfig

# reason di container in stato d'errore (waiting/terminated) usati per marcare un pod "rotto"
ERROR_REASONS = {
    "CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull",
    "CreateContainerConfigError", "CreateContainerError", "RunContainerError",
    "ContainerCannotRun", "OOMKilled", "DeadlineExceeded", "Evicted",
}


def _api():
    try:
        kconfig.load_incluster_config()   # dentro il pod (ServiceAccount)
    except Exception:
        kconfig.load_kube_config()        # fallback locale dev
    return client.CoreV1Api()


# ---------- LISTA POD + STATO (per la pagina Health) ----------
def list_pods(namespaces: list[str]) -> list[dict]:
    """Ritorna i pod dei namespace richiesti con stato sintetico e flag has_error."""
    try:
        v1 = _api()
    except Exception as e:
        return [{"namespace": ",".join(namespaces), "name": "—", "phase": "NO-CLUSTER",
                 "error": f"Kubernetes non disponibile: {e}", "has_error": True,
                 "ready": "0/0", "restarts": 0, "reasons": ["NoKubeconfig"]}]
    out = []
    for ns in namespaces:
        try:
            pods = v1.list_namespaced_pod(ns).items
        except Exception as e:
            out.append({"namespace": ns, "name": "—", "phase": "ERRORE",
                        "error": str(e), "has_error": True, "ready": "0/0",
                        "restarts": 0, "reasons": ["AccessError"]})
            continue
        for p in pods:
            st = p.status
            cs = st.container_statuses or []
            total = len(cs)
            ready = sum(1 for c in cs if c.ready)
            restarts = sum(c.restart_count for c in cs)
            reasons = []
            for c in cs:
                w = c.state.waiting if c.state else None
                t = c.state.terminated if c.state else None
                if w and w.reason:
                    reasons.append(w.reason)
                if t and t.reason and t.reason != "Completed":
                    reasons.append(t.reason)
            phase = st.phase or "Unknown"
            has_error = (
                phase not in ("Running", "Succeeded")
                or any(r in ERROR_REASONS for r in reasons)
                or (phase == "Running" and total and ready < total)
            )
            out.append({
                "name": p.metadata.name,
                "namespace": ns,
                "phase": phase,
                "ready": f"{ready}/{total}",
                "restarts": restarts,
                "reasons": sorted(set(reasons)),
                "has_error": bool(has_error),
            })
    return out


# ---------- LOG SINGOLO POD ----------
def get_pod_log(name: str, namespace: str, tail: int = 200) -> str:
    try:
        v1 = _api()
        return v1.read_namespaced_pod_log(name=name, namespace=namespace, tail_lines=tail)
    except Exception as e:
        return f"[Kubernetes non disponibile / errore lettura log: {e}]"


# ---------- EVENTI POD (equivalente 'kubectl get events') ----------
def get_pod_events(name: str, namespace: str, limit: int = 20) -> str:
    try:
        v1 = _api()
        ev = v1.list_namespaced_event(
            namespace, field_selector=f"involvedObject.name={name}"
        ).items
    except Exception as e:
        return f"[Kubernetes non disponibile / errore lettura eventi: {e}]"
    if not ev:
        return "[nessun evento]"
    ev.sort(key=lambda e: e.last_timestamp or e.metadata.creation_timestamp)
    return "\n".join(
        f"{e.type}/{e.reason} ({e.count or 1}x): {e.message}" for e in ev[-limit:]
    )


# ---------- DESCRIBE POD (equivalente 'kubectl describe') ----------
def describe_pod(name: str, namespace: str) -> str:
    try:
        v1 = _api()
        p = v1.read_namespaced_pod(name, namespace)
    except Exception as e:
        return f"[Kubernetes non disponibile / errore describe: {e}]"
    st = p.status
    lines = [
        f"Pod: {namespace}/{name}",
        f"Phase: {st.phase}",
        f"Node: {p.spec.node_name}",
        f"PodIP: {st.pod_ip}",
    ]
    for c in (st.container_statuses or []):
        if c.state and c.state.waiting:
            state = f"Waiting({c.state.waiting.reason}) {c.state.waiting.message or ''}"
        elif c.state and c.state.terminated:
            t = c.state.terminated
            state = f"Terminated({t.reason}) exit={t.exit_code}"
        elif c.state and c.state.running:
            state = f"Running(since {c.state.running.started_at})"
        else:
            state = "Unknown"
        lines.append(
            f"- container {c.name}: image={c.image} ready={c.ready} "
            f"restarts={c.restart_count} state={state.strip()}"
        )
    for cond in (st.conditions or []):
        lines.append(f"Condition {cond.type}={cond.status} {cond.reason or ''}".rstrip())
    return "\n".join(lines)


# ---------- BUNDLE per l'agente (describe + eventi + log in un colpo) ----------
def gather_bundle(name: str, namespace: str, tail: int = 200) -> dict:
    return {
        "describe": describe_pod(name, namespace),
        "events": get_pod_events(name, namespace),
        "log": get_pod_log(name, namespace, tail),
    }


# ---------- (legacy) dump log multipli — usato da /projects/{id}/analyze ----------
def dump_logs(pods: list[dict], tail: int = 200) -> str:
    """pods = [{name, namespace}]. Ritorna log concatenati etichettati."""
    out = []
    for p in pods:
        name, ns = p.get("name"), p.get("namespace", "default")
        out.append(f"===== POD {ns}/{name} =====\n{get_pod_log(name, ns, tail)}")
    return "\n\n".join(out) if out else "[nessun pod configurato]"
