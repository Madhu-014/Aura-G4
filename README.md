# Aura-G4

Aura-G4 is a medical triage assistant stack with:
- FastAPI backend
- Next.js frontend
- Local Ollama model integration
- Knowledge retrieval from PDF manuals

## Included Manuals (PDF)
The repository includes these triage references:
- `data/triage_manuals/WHO_ETAT_Manual.pdf`
- `data/triage_manuals/Red_Cross_Emergency_Care.pdf`

## Prerequisites
- macOS/Linux (or compatible shell)
- Python 3.10+
- Node.js 18+
- Ollama installed and available in PATH

## 1) Clone
```bash
git clone https://github.com/Madhu-014/Aura-G4.git
cd Aura-G4
```

## 2) Python setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Frontend setup
```bash
cd frontend
npm install
cd ..
```

## 4) Run full stack (recommended)
```bash
chmod +x run_aura_stack.sh
./run_aura_stack.sh
```

This starts:
- Ollama (if not already running)
- Backend at `http://127.0.0.1:8000`
- Frontend at `http://localhost:3000`

## Run manually (optional)
Backend:
```bash
source .venv/bin/activate
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend:
```bash
cd frontend
npm run dev
```

## Quick health check
```bash
curl http://127.0.0.1:8000/health
```

## Project structure
- `backend/` FastAPI app
- `frontend/` Next.js app
- `engine/` model, firewall, retrieval logic
- `data/triage_manuals/` PDF medical references
- `run_aura_stack.sh` one-command startup for local development
