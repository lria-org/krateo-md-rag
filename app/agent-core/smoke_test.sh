#!/usr/bin/env bash
# Smoke test locale — verifica gli endpoint senza Kubernetes.
# Uso: ./smoke_test.sh   (dopo 'docker compose -f docker-compose.test.yml up')
set -e
BASE="http://localhost:8088/api/agent"

# 0) attendi che agent-core completi lo startup (init DB + estensione vector).
#    'up -d' torna subito: senza questa attesa si colpisce l'API prima che sia pronta.
echo "0) attendo readiness di agent-core..."
for i in $(seq 1 30); do
  if curl -sf $BASE/health >/dev/null 2>&1; then
    echo "   pronto (dopo ${i}s)"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "   ❌ timeout: agent-core non risponde. Log: docker compose -f docker-compose.test.yml logs agent-core"
    exit 1
  fi
  sleep 1
done

echo "1) health"
curl -sf $BASE/health && echo

echo "2) config (default ollama gemma2:9b)"
curl -sf $BASE/config && echo

echo "3) crea progetto"
PID=$(curl -sf -X POST $BASE/projects -H 'Content-Type: application/json' \
  -d '{"name":"test-local","pods":[{"name":"demo-pod","namespace":"krateo-demo"}]}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "   project id=$PID"

echo "4) upload MD di prova (test embeddings Ollama + pgvector)"
echo "# Krateo Runbook
Se il pod va in CrashLoopBackOff controllare la variabile NUQ_DATABASE_URL.
La porta di Firecrawl e' la 3002." > /tmp/kb_test.md
curl -sf -X POST $BASE/projects/$PID/upload -F "file=@/tmp/kb_test.md" && echo

echo "5) query RAG (retrieval, no LLM)"
curl -sf -X POST $BASE/projects/$PID/rag -H 'Content-Type: application/json' \
  -d '{"query":"porta di firecrawl","k":3}' && echo

echo
echo "OK base. /logs e /analyze richiedono kubeconfig (vedi compose)."
