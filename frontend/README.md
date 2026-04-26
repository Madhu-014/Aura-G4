# Aura-G4 Frontend

## Run

1. Install frontend dependencies:
   npm install
2. Start backend API in a separate terminal (from repo root):
   /Users/madhusudhan/Documents/Aura-G4/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
3. Start frontend dev server:
   npm run dev

## Notes

- Expects FastAPI backend at `NEXT_PUBLIC_API_BASE`.
- Uses tactical obsidian theme with live telemetry polling.

## Troubleshooting

- If you see 404 or failed network calls in the UI, verify backend is running on port 8000:
  curl http://127.0.0.1:8000/health
- Expected response should be HTTP 200.

## One Command Startup

From repository root, run:

```bash
./run_aura_stack.sh
```

This script starts:

- Ollama service (if not already running)
- FastAPI backend on `127.0.0.1:8000`
- Next.js frontend on `localhost:3000`

Logs are written to `.logs/` in the repository root.
