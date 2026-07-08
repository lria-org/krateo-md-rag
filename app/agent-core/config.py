"""Runtime config. Default = Ollama locale. Sovrascrivibile da UI web via POST /api/agent/config."""
import os

# stato mutabile in-memory (UI puo' cambiarlo a caldo, no restart)
SETTINGS = {
    "provider": os.getenv("EMBED_PROVIDER", "ollama"),        # ollama | openai
    "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
    "embed_model": os.getenv("MODEL_EMBEDDING_NAME", "nomic-embed-text"),
    "chat_model": os.getenv("MODEL_NAME", "gemma2:9b"),
    "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
}

# dim colonna vettoriale: FISSA a livello DB (deve combaciare col modello scelto).
# nomic-embed-text=768, mxbai-embed-large=1024, openai text-embedding-3-small=1536
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

DB_DSN = os.getenv(
    "AGENT_DB_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)


def get_settings() -> dict:
    return dict(SETTINGS)


def update_settings(patch: dict) -> dict:
    for k, v in patch.items():
        if k in SETTINGS and v is not None:
            SETTINGS[k] = v
    return get_settings()
