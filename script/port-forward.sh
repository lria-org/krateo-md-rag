#!/bin/bash

PORT=31181
# Stack gestito da Argo/Krateo (composition krateo-md-rag-fbc2dv66) nel namespace fireworks-app.
NAMESPACE="fireworks-app"
SERVICE="krateo-md-rag-fbc2dv66-fireworks-app-skeleton"

echo "🔄 Pulizia: controllo se ci sono vecchi tunnel aperti sulla porta $PORT..."

# Cerca se la porta è già occupata da un vecchio port-forward e lo killa
PID=$(lsof -t -i:$PORT)
if [ ! -z "$PID" ]; then
    echo "💀 Trovato tunnel residuo (PID: $PID). Lo chiudo..."
    kill -9 $PID
    sleep 1
fi

echo "🔌 Attivo il nuovo port-forward per $SERVICE ($PORT -> $PORT)..."

# Avvia il port-forward deviando i log nel nulla e mandando il processo in background (&)
kubectl port-forward svc/$SERVICE $PORT:$PORT -n $NAMESPACE > /dev/null 2>&1 &

# Aspetta due secondi per dare il tempo a Kubernetes di agganciarsi
sleep 2

# Controllo finale di conferma
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "--------------------------------------------------------"
    echo "✅ TUNNEL ATTIVO IN BACKGROUND!"
    echo "🌐 Apri il browser su: http://localhost:$PORT"
    echo "--------------------------------------------------------"
else
    echo "❌ Errore: Il tunnel non è partito. Controlla lo stato del Pod con 'kubectl get pods -n $NAMESPACE'"
fi