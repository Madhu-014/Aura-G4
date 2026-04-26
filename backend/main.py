from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import psutil
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from engine.firewall import AuraFirewall, FirewallDecision
from engine.gemma_client import AuraEngine


class ValidateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class ValidateResponse(BaseModel):
    allowed: bool
    reason: str
    score: float = 0.0
    violation_code: Optional[str] = None
    redirect_message: Optional[str] = None


class TriageStreamRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    history: Optional[List[Dict[str, str]]] = None
    prefer_complex: bool = False


class TelemetryResponse(BaseModel):
    cpu_percent: float
    ram_percent: float
    mps_allocated_mb: float
    npu_heartbeat: str
    tokens_per_second: float
    active_model: str
    firewall_status: Dict[str, Any]


class ManualsResponse(BaseModel):
    manuals: List[str]


app = FastAPI(title="Aura-G4 Tactical API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AuraEngine()
firewall = AuraFirewall()

_telemetry_state: Dict[str, Any] = {
    "tokens_per_second": 0.0,
    "active_model": engine.fast_model,
    "last_stream_ts": 0.0,
    "last_violation_code": None,
}


def _as_validate_response(decision: FirewallDecision) -> ValidateResponse:
    return ValidateResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        score=decision.score,
        violation_code=decision.violation_code,
        redirect_message=decision.redirect_message,
    )


def _validate_prompt(prompt: str) -> FirewallDecision:
    # Firewall is hard-wired and cannot be bypassed by request path.
    return firewall.validate_intent(prompt)


def _npu_heartbeat(last_stream_ts: float) -> str:
    if not last_stream_ts:
        return "IDLE"
    age = time.time() - last_stream_ts
    if age < 3:
        return "ACTIVE"
    if age < 12:
        return "WARM"
    return "IDLE"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/validate", response_model=ValidateResponse)
def validate(request: ValidateRequest) -> ValidateResponse:
    decision = _validate_prompt(request.prompt)
    return _as_validate_response(decision)


@app.post("/api/triage/stream")
async def triage_stream(request: TriageStreamRequest) -> StreamingResponse:
    decision = _validate_prompt(request.prompt)
    if not decision.allowed:
        _telemetry_state["last_violation_code"] = decision.violation_code
        raise HTTPException(
            status_code=403,
            detail={
                "allowed": False,
                "reason": decision.reason,
                "score": decision.score,
                "violation_code": decision.violation_code,
                "redirect_message": decision.redirect_message,
            },
        )

    async def event_stream() -> AsyncGenerator[bytes, None]:
        start = time.time()
        raw_len = 0
        token_count = 0
        rag_sources_sent = False

        try:
            for frame in engine.stream_triage_response(
                user_prompt=request.prompt,
                history=request.history,
                prefer_complex=request.prefer_complex,
            ):
                _telemetry_state["last_stream_ts"] = time.time()
                if frame.safety_violation_code:
                    _telemetry_state["last_violation_code"] = frame.safety_violation_code

                delta = frame.raw[raw_len:]
                raw_len = len(frame.raw)
                if delta:
                    token_count += len(delta.split())

                rag_sources = None
                if not rag_sources_sent and frame.rag_sources:
                    rag_sources = frame.rag_sources
                    rag_sources_sent = True

                payload = {
                    "delta": delta,
                    "raw": frame.raw,
                    "think": frame.think,
                    "final": frame.final,
                    "tool_name": frame.tool_name,
                    "tool_payload": frame.tool_payload,
                    "was_intercepted": frame.was_intercepted,
                    "safety_violation_code": frame.safety_violation_code,
                    "rag_sources": rag_sources,
                }
                yield f"data: {json.dumps(payload)}\n\n".encode("utf-8")

            elapsed = max(time.time() - start, 1e-6)
            _telemetry_state["tokens_per_second"] = token_count / elapsed
            _telemetry_state["active_model"] = engine.fast_model
            done = {"done": True, "tokens_per_second": _telemetry_state["tokens_per_second"]}
            yield f"data: {json.dumps(done)}\n\n".encode("utf-8")

        except Exception as exc:
            error_payload = {"error": str(exc), "done": True}
            yield f"data: {json.dumps(error_payload)}\n\n".encode("utf-8")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/vision")
async def vision(
    file: UploadFile = File(...),
    prompt: str = Form(default="Analyze hazards and extraction approach."),
) -> JSONResponse:
    suffix = os.path.splitext(file.filename or "upload.jpg")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(prefix="aura_vision_", suffix=suffix, delete=False) as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    try:
        result = engine.process_field_intel(temp_path, prompt)
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "raw": str(exc),
                "think": "",
                "final": f"Vision service unavailable: {exc}",
            },
        )
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


@app.get("/api/telemetry", response_model=TelemetryResponse)
def telemetry() -> TelemetryResponse:
    cpu = psutil.cpu_percent(interval=0.0)
    ram = psutil.virtual_memory().percent

    mps_allocated_mb = 0.0
    if torch.backends.mps.is_available():
        try:
            mps_allocated_mb = torch.mps.current_allocated_memory() / (1024 * 1024)
        except Exception:
            mps_allocated_mb = 0.0

    return TelemetryResponse(
        cpu_percent=cpu,
        ram_percent=ram,
        mps_allocated_mb=round(mps_allocated_mb, 2),
        npu_heartbeat=_npu_heartbeat(_telemetry_state.get("last_stream_ts", 0.0)),
        tokens_per_second=round(float(_telemetry_state.get("tokens_per_second", 0.0)), 3),
        active_model=str(_telemetry_state.get("active_model", engine.fast_model)),
        firewall_status=firewall.runtime_status(),
    )


@app.get("/api/manuals", response_model=ManualsResponse)
def manuals() -> ManualsResponse:
    try:
        loaded = engine.list_loaded_manuals()
    except Exception:
        loaded = []
    return ManualsResponse(manuals=loaded)
