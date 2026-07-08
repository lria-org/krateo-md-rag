"""Client embedding + chat. Provider configurabile a caldo (Ollama default / OpenAI)."""
import httpx
from config import get_settings

RCA_PROMPT = """Sei un Agente di Supporto Esperto per la piattaforma Krateo PlatformOps.
Analizza i log reali dei pod e confrontali con la Knowledge Base (RAG) per identificare
disallineamenti, bug noti o problemi architetturali.

[KNOWLEDGE BASE PERTINENTE DALLA RAG]
{rag_context}

[LOG REALI DEI POD KUBERNETES CORRENTI]
{kubernetes_logs}

Genera un report strutturato:
1. **Stato dei Pod**
2. **Problemi Rilevati**
3. **Root Cause Analysis (RCA)**
4. **Azioni Correttive Consigliate** (comandi kubectl / patch YAML)
"""


def embed(text: str) -> list[float]:
    s = get_settings()
    if s["provider"] == "openai":
        r = httpx.post(
            f'{s["openai_base_url"] or "https://api.openai.com/v1"}/embeddings',
            headers={"Authorization": f'Bearer {s["openai_api_key"]}'},
            json={"model": s["embed_model"], "input": text},
            timeout=60,
        )
        r.raise_for_status()
        # forza tutti i valori a float: alcuni provider ritornano int misti a float
        # (es. 0 senza decimali) e psycopg rifiuta gli array a tipi misti.
        return [float(x) for x in r.json()["data"][0]["embedding"]]
    # ollama
    r = httpx.post(
        f'{s["ollama_base_url"]}/api/embeddings',
        json={"model": s["embed_model"], "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return [float(x) for x in r.json()["embedding"]]


def chat(prompt: str) -> str:
    s = get_settings()
    if s["provider"] == "openai":
        r = httpx.post(
            f'{s["openai_base_url"] or "https://api.openai.com/v1"}/chat/completions',
            headers={"Authorization": f'Bearer {s["openai_api_key"]}'},
            json={"model": s["chat_model"], "messages": [{"role": "user", "content": prompt}]},
            timeout=180,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    # ollama
    r = httpx.post(
        f'{s["ollama_base_url"]}/api/generate',
        json={"model": s["chat_model"], "prompt": prompt, "stream": False},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["response"]


def build_rca_prompt(rag_context: str, kubernetes_logs: str) -> str:
    return RCA_PROMPT.format(rag_context=rag_context, kubernetes_logs=kubernetes_logs)
