"""agent-core: orchestratore RAG + Log Analysis + RCA.
Endpoint SEPARATI: ogni chiamata fa una cosa sola. /analyze compone gli altri, non li duplica.
Montato da Nginx su /api/agent/*  (porta interna 8000)."""
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

import db
import llm
import k8s
from config import get_settings, update_settings

app = FastAPI(title="krateo-agent-core", version="0.1.0")


@app.on_event("startup")
def _startup():
    db.init_db()


# ---------- MODELS ----------
class PodRef(BaseModel):
    name: str
    namespace: str = "default"


class ProjectIn(BaseModel):
    name: str
    pods: list[PodRef] = []


class ConfigPatch(BaseModel):
    provider: str | None = None
    ollama_base_url: str | None = None
    embed_model: str | None = None
    chat_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None


# ---------- HEALTH ----------
@app.get("/api/agent/health")
def health():
    return {"status": "ok"}


# ---------- CONFIG (UI web) ----------
@app.get("/api/agent/config")
def read_config():
    s = get_settings()
    s.pop("openai_api_key", None)  # non esporre segreti
    return s


@app.post("/api/agent/config")
def write_config(patch: ConfigPatch):
    s = update_settings(patch.model_dump(exclude_none=True))
    s.pop("openai_api_key", None)
    return s


# ---------- PROJECTS ----------
@app.post("/api/agent/projects")
def create_project(p: ProjectIn):
    return db.create_project(p.name, [pod.model_dump() for pod in p.pods])


@app.get("/api/agent/projects")
def list_projects():
    return db.list_projects()


# ---------- UPLOAD (solo ingest) ----------
def _chunk(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


@app.post("/api/agent/projects/{pid}/upload")
async def upload(pid: int, file: UploadFile = File(...)):
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    raw = (await file.read()).decode("utf-8", errors="ignore")
    chunks = _chunk(raw)
    pairs = [(c, llm.embed(c)) for c in chunks]
    db.insert_chunks(pid, pairs)
    return {"project_id": pid, "chunks": len(pairs)}


# ---------- LOGS (solo dump k8s, no LLM) ----------
@app.post("/api/agent/projects/{pid}/logs")
def logs(pid: int):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "project not found")
    return {"logs": k8s.dump_logs(proj["pods"])}


# ---------- RAG (solo retrieval, no LLM) ----------
class Query(BaseModel):
    query: str
    k: int = 5


@app.post("/api/agent/projects/{pid}/rag")
def rag(pid: int, q: Query):
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    emb = llm.embed(q.query)
    return {"context": db.search_chunks(pid, emb, q.k)}


# ---------- ANALYZE (orchestratore: compone logs+rag+llm) ----------
@app.post("/api/agent/projects/{pid}/analyze")
def analyze(pid: int):
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(404, "project not found")
    logs_txt = k8s.dump_logs(proj["pods"])
    kb = db.search_chunks(pid, llm.embed(logs_txt[:2000]), k=5)
    prompt = llm.build_rca_prompt("\n---\n".join(kb), logs_txt)
    return {"report": llm.chat(prompt)}


# ========== HEALTH PAGE: esplorazione pod + RCA su singolo pod ==========
DEFAULT_NS = "krateo-system,krateo-demo"


class PodAnalyzeIn(BaseModel):
    name: str
    namespace: str
    project_id: int | None = None   # se assente -> RAG globale


# lista pod dei namespace (default: namespace krateo) con stato/errori
@app.get("/api/agent/k8s/pods")
def k8s_pods(namespaces: str = DEFAULT_NS):
    ns = [n.strip() for n in namespaces.split(",") if n.strip()]
    return {"pods": k8s.list_pods(ns)}


# log di un singolo pod (per la vista log al click)
@app.get("/api/agent/k8s/pods/{namespace}/{name}/log")
def k8s_pod_log(namespace: str, name: str, tail: int = 200):
    return {"pod": f"{namespace}/{name}", "log": k8s.get_pod_log(name, namespace, tail)}


# 🧠 agente: raccoglie bundle (describe+eventi+log) + RAG (sempre) -> RCA LLM
@app.post("/api/agent/k8s/analyze")
def k8s_analyze(p: PodAnalyzeIn):
    bundle = k8s.gather_bundle(p.name, p.namespace)
    ctx = (
        f"### DESCRIBE\n{bundle['describe']}\n\n"
        f"### EVENTI\n{bundle['events']}\n\n"
        f"### LOG\n{bundle['log']}"
    )
    emb = llm.embed(ctx[:2000])
    kb = db.search_chunks(p.project_id, emb, 5) if p.project_id else db.search_all(emb, 5)
    prompt = llm.build_rca_prompt("\n---\n".join(kb), ctx)
    return {"pod": f"{p.namespace}/{p.name}", "bundle": bundle, "report": llm.chat(prompt)}
