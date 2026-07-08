"""Accesso Postgres + pgvector. Schema isolato 'agent' (non tocca tabelle Firecrawl)."""
import psycopg
from pgvector.psycopg import register_vector
from config import DB_DSN, EMBED_DIM

DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS agent;
CREATE TABLE IF NOT EXISTS agent.projects (
    id      SERIAL PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL,
    pods    JSONB NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS agent.documents_embeddings (
    id         SERIAL PRIMARY KEY,
    project_id INT REFERENCES agent.projects(id) ON DELETE CASCADE,
    chunk      TEXT NOT NULL,
    embedding  vector({EMBED_DIM})
);
CREATE INDEX IF NOT EXISTS idx_doc_emb_project
    ON agent.documents_embeddings (project_id);
"""


def conn():
    c = psycopg.connect(DB_DSN, autocommit=True)
    register_vector(c)  # richiede che il tipo 'vector' esista gia' (CREATE EXTENSION fatto)
    return c


def init_db():
    # 1) bootstrap con connessione RAW: il tipo 'vector' non esiste ancora,
    #    quindi NON si puo' chiamare register_vector qui. Prima crea l'estensione.
    with psycopg.connect(DB_DSN, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # 2) ora il tipo 'vector' esiste: conn() puo' registrarlo e creare schema/tabelle.
    with conn() as c:
        c.execute(DDL)


# --- projects ---
def create_project(name: str, pods: list) -> dict:
    """Idempotente (get-or-create): se il nome esiste, aggiorna i pod e ritorna
    il progetto esistente invece di fallire con UniqueViolation. Cosi' re-ingest
    dello stesso sito o re-run dello smoke test non danno 500."""
    import json
    with conn() as c:
        row = c.execute(
            """INSERT INTO agent.projects(name, pods) VALUES(%s, %s)
               ON CONFLICT (name) DO UPDATE SET
                 pods = CASE WHEN EXCLUDED.pods = '[]'::jsonb
                             THEN agent.projects.pods ELSE EXCLUDED.pods END
               RETURNING id, name, pods""",
            (name, json.dumps(pods)),
        ).fetchone()
    return {"id": row[0], "name": row[1], "pods": row[2]}


def list_projects() -> list:
    with conn() as c:
        rows = c.execute("SELECT id, name, pods FROM agent.projects ORDER BY id").fetchall()
    return [{"id": r[0], "name": r[1], "pods": r[2]} for r in rows]


def get_project(pid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT id, name, pods FROM agent.projects WHERE id=%s", (pid,)).fetchone()
    return {"id": r[0], "name": r[1], "pods": r[2]} if r else None


# --- embeddings ---
def insert_chunks(pid: int, pairs: list[tuple[str, list]]):
    with conn() as c:
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO agent.documents_embeddings(project_id, chunk, embedding) VALUES(%s,%s,%s)",
                [(pid, txt, emb) for txt, emb in pairs],
            )


def _vec(emb: list) -> str:
    """Serializza l'embedding nel literal testuale di pgvector '[1,2,3]'.
    Va usato con cast esplicito %s::vector: l'operatore <=> non fa cast
    impliciti da array Postgres a vector (a differenza dell'INSERT)."""
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def search_chunks(pid: int, query_emb: list, k: int = 5) -> list[str]:
    with conn() as c:
        rows = c.execute(
            """SELECT chunk FROM agent.documents_embeddings
               WHERE project_id=%s
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (pid, _vec(query_emb), k),
        ).fetchall()
    return [r[0] for r in rows]


def search_all(query_emb: list, k: int = 5) -> list[str]:
    """Retrieval globale su tutta la KB (nessun filtro progetto).
    Usato dalla pagina Health quando non si seleziona un progetto specifico."""
    with conn() as c:
        rows = c.execute(
            """SELECT chunk FROM agent.documents_embeddings
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (_vec(query_emb), k),
        ).fetchall()
    return [r[0] for r in rows]
