#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_PY="$ROOT_DIR/.venv/bin/python"
BACKEND_LOG="$ROOT_DIR/.logs/backend.log"
FRONTEND_LOG="$ROOT_DIR/.logs/frontend.log"
OLLAMA_LOG="$ROOT_DIR/.logs/ollama.log"

mkdir -p "$ROOT_DIR/.logs"

pids=()

kill_port_if_busy() {
  local port="$1"
  local pid
  pid="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [[ -n "$pid" ]]; then
    echo "[Aura-G4] Releasing port $port (PID $pid)..."
    kill "$pid" 2>/dev/null || true
  fi
}

wait_for_http() {
  local url="$1"
  local max_tries="${2:-40}"
  local i
  for i in $(seq 1 "$max_tries"); do
    if curl -s "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

cleanup() {
  echo
  echo "[Aura-G4] Shutting down services..."
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait || true
  echo "[Aura-G4] Shutdown complete."
}
trap cleanup EXIT INT TERM

command -v ollama >/dev/null 2>&1 || {
  echo "[Aura-G4] Error: ollama CLI not found in PATH."
  exit 1
}

if [[ ! -x "$VENV_PY" ]]; then
  echo "[Aura-G4] Error: Python virtualenv not found at $VENV_PY"
  exit 1
fi

if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "[Aura-G4] Starting Ollama service..."
  ollama serve >"$OLLAMA_LOG" 2>&1 &
  pids+=("$!")
  if ! wait_for_http "http://127.0.0.1:11434/api/tags" 60; then
    echo "[Aura-G4] Error: Ollama did not become ready in time. Check $OLLAMA_LOG"
    exit 1
  fi
else
  echo "[Aura-G4] Ollama already running."
fi

kill_port_if_busy 8000
kill_port_if_busy 3000

echo "[Aura-G4] Starting FastAPI backend..."
cd "$ROOT_DIR"
"$VENV_PY" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 >"$BACKEND_LOG" 2>&1 &
pids+=("$!")

if ! wait_for_http "http://127.0.0.1:8000/health" 60; then
  echo "[Aura-G4] Error: Backend did not become ready in time. Check $BACKEND_LOG"
  exit 1
fi

echo "[Aura-G4] Starting Next.js frontend..."
npm --prefix "$FRONTEND_DIR" run dev >"$FRONTEND_LOG" 2>&1 &
pids+=("$!")

if ! wait_for_http "http://127.0.0.1:3000" 60; then
  echo "[Aura-G4] Error: Frontend did not become ready in time. Check $FRONTEND_LOG"
  exit 1
fi

echo "[Aura-G4] Services running:"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://127.0.0.1:8000"
echo "  Logs:     $ROOT_DIR/.logs"
echo "[Aura-G4] Press Ctrl+C to stop all services."

wait
