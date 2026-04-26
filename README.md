# Aura-G4

Gemma-powered tactical triage assistant for high-pressure emergency scenarios.

Aura-G4 combines local LLM reasoning, protocol-grounded retrieval, and hard safety gating to help responders move from uncertainty to action faster.

## Why This Matters

In emergency response, delayed or unsafe decisions can cost lives. Aura-G4 is built for the moment when teams need:
- Fast, structured triage support
- Protocol-consistent recommendations
- Reliable behavior under unsafe or off-domain prompts
- Local-first operation with minimal cloud dependency

## Hackathon Focus

This project is designed as a Kaggle Gemma Hackathon submission and showcases:
- Gemma-driven medical reasoning and extraction workflows
- Retrieval-augmented grounding from authoritative triage manuals
- Defensive AI architecture with an explicit firewall layer
- Real-time telemetry and streaming output for operational trust

## Key Features

- Gemma reasoning engine
	- Local inference orchestration via Ollama in [engine/gemma_client.py](engine/gemma_client.py)
	- Fast/complex model routing and runtime fallback behavior

- Safety-first guardrails
	- Mandatory prompt firewall in [engine/firewall.py](engine/firewall.py)
	- Unsafe or out-of-scope requests are blocked before generation

- Protocol-grounded RAG
	- PDF ingestion + vector retrieval in [engine/knowledge_base.py](engine/knowledge_base.py)
	- Response context sourced from emergency manuals

- Streaming triage experience
	- SSE streaming endpoint in [backend/main.py](backend/main.py)
	- Incremental reasoning output and final actionable summary

- Vision-assisted field intel
	- Image + prompt analysis endpoint in [backend/main.py](backend/main.py)

- Live operational telemetry
	- CPU, RAM, model activity, and throughput metrics from [backend/main.py](backend/main.py)

## Architecture

1. User submits a triage prompt from the Next.js interface.
2. Backend validates intent through the firewall.
3. Engine retrieves relevant protocol snippets from local manuals.
4. Gemma generates structured triage guidance with grounded context.
5. Results stream to UI in real time, with telemetry updates.

Core components:
- Frontend: [frontend](frontend)
- API server: [backend/main.py](backend/main.py)
- Gemma orchestration: [engine/gemma_client.py](engine/gemma_client.py)
- Safety firewall: [engine/firewall.py](engine/firewall.py)
- Knowledge retrieval: [engine/knowledge_base.py](engine/knowledge_base.py)

## Included Medical References (PDF)

Bundled with the repository:
- [data/triage_manuals/WHO_ETAT_Manual.pdf](data/triage_manuals/WHO_ETAT_Manual.pdf)
- [data/triage_manuals/Red_Cross_Emergency_Care.pdf](data/triage_manuals/Red_Cross_Emergency_Care.pdf)

## Quick Start (Judge-Friendly)

Prerequisites:
- Python 3.10+
- Node.js 18+
- Ollama installed and available in PATH
- macOS/Linux shell

1. Clone

		git clone https://github.com/Madhu-014/Aura-G4.git
		cd Aura-G4

2. Python environment

		python3 -m venv .venv
		source .venv/bin/activate
		pip install --upgrade pip
		pip install -r requirements.txt

3. Frontend dependencies

		cd frontend
		npm install
		cd ..

4. Start full stack

		chmod +x run_aura_stack.sh
		./run_aura_stack.sh

Services:
- Frontend: http://localhost:3000
- Backend: http://127.0.0.1:8000

Health check:

		curl http://127.0.0.1:8000/health

## Manual Run (Optional)

Backend:

		source .venv/bin/activate
		python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

Frontend:

		cd frontend
		npm run dev

## API Surface

Implemented in [backend/main.py](backend/main.py):
- GET /health
- POST /api/validate
- POST /api/triage/stream
- POST /api/vision
- GET /api/telemetry
- GET /api/manuals

## Demo Flow (Recommended for Judges)

1. Open the app and submit a realistic triage scenario.
2. Show streaming response behavior and structured action guidance.
3. Trigger an unsafe prompt to demonstrate firewall interception.
4. Upload a field image for vision-assisted hazard analysis.
5. Open telemetry to show system health and model throughput.

## Innovation Highlights

- Safety is first-class, not bolted on.
- Retrieval grounding is rooted in practical emergency manuals.
- Streaming UX makes model thinking transparent and operationally useful.
- Local-first design supports constrained-connectivity environments.

## Responsible AI Notes

- Aura-G4 is a decision-support system, not a replacement for clinicians or emergency professionals.
- Always verify recommendations against local medical protocols and trained personnel judgment.
- Firewall controls reduce misuse risk by rejecting unsafe and irrelevant prompts.

## Repository Structure

- [app.py](app.py): Streamlit prototype entrypoint
- [backend](backend): FastAPI service
- [engine](engine): Gemma orchestration, safety, retrieval
- [frontend](frontend): Next.js dashboard UI
- [modules](modules): auxiliary triage/vision helpers
- [data/triage_manuals](data/triage_manuals): source medical documents
- [run_aura_stack.sh](run_aura_stack.sh): one-command local startup
- [requirements.txt](requirements.txt): unified Python dependencies

## Roadmap

- Add multilingual triage support for low-resource regions
- Expand protocol corpus and citation granularity
- Introduce scenario simulation benchmarking suite
- Improve offline packaging for rapid field deployment

## Team Note

Built to demonstrate how Gemma can be applied to real-world, high-stakes public-impact workflows with safety, transparency, and practical deployment in mind.
