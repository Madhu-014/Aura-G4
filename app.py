"""Aura-G4 Tactical Command Center UI."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Any, Dict, List

from PIL import Image
import psutil
import streamlit as st

from engine.gemma_client import AuraEngine


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "field_images"
CSS_FILE = BASE_DIR / "assets" / "style.css"


def load_css() -> None:
    if CSS_FILE.exists():
        st.markdown(f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def init_state() -> None:
    # Keep engine cached to avoid repeated model/firewall initialization.
    st.session_state.setdefault("engine", AuraEngine())
    st.session_state.setdefault("vision_report", None)
    st.session_state.setdefault("latest_field_report", None)
    st.session_state.setdefault("latest_protocol", None)
    st.session_state.setdefault("rag_sources", [])
    st.session_state.setdefault("latest_tps", 0.0)
    st.session_state.setdefault("last_model", "gemma4:e4b")
    st.session_state.setdefault("risk_score", 0.0)
    st.session_state.setdefault("scan_active", False)
    st.session_state.setdefault("blocked", False)
    st.session_state.setdefault("blocked_code", "")
    st.session_state.setdefault("think_trace", "")
    st.session_state.setdefault("final_output", "")


def save_uploaded_image(uploaded_file) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uploaded_file.name}"
    image_path = UPLOAD_DIR / filename
    image_path.write_bytes(uploaded_file.getbuffer())
    return image_path


def clean_think_text(text: str) -> str:
    cleaned = (text or "").replace("<|think|>", "")
    cleaned = cleaned.replace("</think>", "")
    cleaned = cleaned.replace("<|channel|>thought", "")
    cleaned = cleaned.replace("<|channel>thought", "")
    return cleaned.strip()


def heartbeat_state(online: bool) -> str:
    if st.session_state.get("blocked"):
        return "hb-blocked"
    if st.session_state.get("scan_active"):
        return "hb-thinking"
    if online:
        return "hb-standby"
    return "hb-offline"


def render_header(engine: AuraEngine, manuals: List[str]) -> None:
    online = engine.is_ollama_online()
    online_text = "ONLINE" if online else "OFFLINE"
    hb_class = heartbeat_state(online)
    model_text = str(st.session_state.get("last_model", engine.fast_model))

    st.markdown(
        "<section class='header-shell'>"
        "<div class='header-center'>"
        "<div class='header-kicker'><span class='system-name-mark'>AURA-G4</span></div>"
        "<h1 class='header-title'>Tactical Operations Center</h1>"
        "<p class='header-subtitle'>"
        "Ingest field visuals, validate intent through neural shielding, and deliver grounded triage actions from local protocols."
        "</p>"
        "<div class='header-meta-line-wrap'>"
        f"<div class='header-meta-line'>MODEL {model_text}</div>"
        f"<div class='header-meta-line'>PDFS {len(manuals)}</div>"
        "</div>"
        f"<div class='online-pill'><span class='heartbeat-dot {hb_class}'></span>{online_text}</div>"
        "</div>"
        "</section>",
        unsafe_allow_html=True,
    )


def meter_row_html(label: str, value: float, color: str) -> str:
    bounded = max(0.0, min(100.0, value))
    return (
        "<div class='meter-row'>"
        f"<div class='meter-line'><span class='meter-label'>{label}</span><span class='meter-val'>{bounded:.1f}%</span></div>"
        "<div class='meter-track'>"
        f"<span class='meter-fill' style='width:{bounded:.1f}%; background:{color};'></span>"
        "</div>"
        "</div>"
    )


def render_manual_table(manuals: List[str]) -> None:
    if not manuals:
        st.caption("No manuals indexed.")
        return

    rows = "".join([f"<tr><td>{idx + 1:02d}</td><td>{name}</td></tr>" for idx, name in enumerate(manuals)])
    st.markdown(
        "<table class='manual-table'>"
        "<thead><tr><th>#</th><th>Manual</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>",
        unsafe_allow_html=True,
    )


def render_sidebar_monitor(engine: AuraEngine, manuals: List[str]) -> None:
    cpu = psutil.cpu_percent(interval=0.08)
    vm = psutil.virtual_memory()
    vram = vm.percent
    fw_state = engine.firewall.runtime_status()

    fw_active = "ACTIVE" if fw_state.get("model_loaded") else "STANDBY"
    fw_backend = str(fw_state.get("backend", "unknown")).replace("_", " ").upper()
    fw_device = str(fw_state.get("device", "cpu")).upper()
    npu_state = "THINKING" if st.session_state.get("scan_active") else "STANDBY"
    risk_score = float(st.session_state.get("risk_score", 0.0))

    with st.sidebar:
        st.markdown(
            "<div class='side-monitor-title'>"
            "<div class='side-monitor-kicker'><span class='system-name-mark'>AURA-G4</span></div>"
            "<div class='side-monitor-main'>System Monitor</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown(meter_row_html("CPU", cpu, "#00FF65"), unsafe_allow_html=True)
        st.markdown(meter_row_html("RAM", vm.percent, "#00FF65"), unsafe_allow_html=True)
        st.markdown(meter_row_html("VRAM", vram, "#2C9DFF"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            "<div class='sidebar-card side-state'>"
            "<div class='side-head'>Device Status</div>"
            f"<div class='side-line'>NPU {npu_state}</div>"
            f"<div class='side-line'>FIREWALL {fw_active}</div>"
            f"<div class='side-line'>BACKEND {fw_backend}</div>"
            f"<div class='side-line'>DEVICE {fw_device}</div>"
            f"<div class='side-line'>TOK/S {st.session_state.get('latest_tps', 0.0):.2f}</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(risk_bar_html(risk_score), unsafe_allow_html=True)

        with st.expander("[DOC] MISSION PROTOCOLS", expanded=True):
            if st.button("Refresh Manuals", use_container_width=True, key="refresh_manuals_btn"):
                with st.status("Refreshing protocol index...", expanded=False):
                    engine.refresh_knowledge_base(str(DATA_DIR))
                    st.success("Manual index updated")
                st.rerun()
            render_manual_table(manuals)


def render_reticle_preview(image_path: Path) -> None:
    image = Image.open(image_path)
    width, height = image.size
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    ext = image_path.suffix.replace(".", "") or "jpeg"

    st.markdown(
        "<div class='reticle-wrap'>"
        f"<img src='data:image/{ext};base64,{encoded}' alt='Field image preview' />"
        "<div class='reticle'></div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='meta-block'>"
        f"RES {width}x{height} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_field_intelligence(engine: AuraEngine) -> None:
    st.markdown(
        "<div class='section-header center'>"
        "<div class='section-kicker'>Acquisition</div>"
        "<div class='section-title'>Field Intelligence</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader("Disaster Image", type=["png", "jpg", "jpeg", "webp"], key="field_uploader")
    query = st.text_area(
        "Intel Query",
        key="vision_query",
        height=130,
        placeholder="Identify hazards, structural collapse risk, responder ingress, and casualty indicators.",
    )

    if uploaded is not None:
        image_path = save_uploaded_image(uploaded)
        render_reticle_preview(image_path)

        if st.button("Analyze Field Intel", use_container_width=True, key="analyze_field_intel"):
            with st.status("Running multimodal hazard extraction...", expanded=False):
                st.session_state.vision_report = engine.process_field_intel(str(image_path), query)
                st.success("Field analysis complete")

    if st.session_state.get("vision_report"):
        final_assessment = st.session_state.vision_report.get("final", "No output")
        st.markdown(
            "<div class='vision-assessment-card'>"
            "<div class='report-head'>Vision Assessment</div>"
            f"<div class='answer-body'>{_escape_html(final_assessment)}</div>"
            "</div>",
            unsafe_allow_html=True,
        )




def risk_bar_html(risk_score: float) -> str:
    risk_pct = max(0.0, min(100.0, risk_score * 100.0))
    if risk_pct <= 20:
        tone = "LOW"
        color = "#00FF65"
    elif risk_pct <= 45:
        tone = "ELEVATED"
        color = "#FFD166"
    else:
        tone = "HIGH"
        color = "#FF4D5B"

    return (
        "<div class='risk-shell'>"
        "<div class='risk-head'><span>Risk Assessment</span>"
        f"<span class='risk-value'>{risk_pct:.1f}% {tone}</span></div>"
        "<div class='risk-track'>"
        f"<span class='risk-fill' style='width:{risk_pct:.1f}%; background:{color};'></span>"
        "</div>"
        "</div>"
    )


def process_trace_html(think_text: str, tps: float, thinking: bool = False) -> str:
    content = clean_think_text(think_text) or "Waiting for reasoning stream..."
    state_class = "trace-thinking" if thinking else "trace-idle"
    return (
        f"<div class='trace-shell {state_class}'>"
        "<div class='trace-head'>Neural Trace</div>"
        f"<pre class='trace-body'>{content}</pre>"
        "</div>"
    )


def answer_card_html(answer_text: str) -> str:
    content = answer_text or "Awaiting triage output..."
    return (
        "<div class='answer-shell'>"
        "<div class='answer-head'>AI Answer</div>"
        f"<div class='answer-body'>{content}</div>"
        "</div>"
    )


def confidence_pct(score: Any) -> float:
    """Convert raw distance score to a bounded confidence percentage."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.0, min(100.0, (1.0 - value) * 100.0))


def confidence_badge_html(score: Any) -> str:
    conf = confidence_pct(score)
    if conf > 90.0:
        tier = "conf-high"
    elif conf >= 75.0:
        tier = "conf-mid"
    else:
        tier = "conf-low"
    return f"<span class='conf-badge {tier}'>{conf:.1f}% Match</span>"


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def infer_supplies_from_context(rag_sources: List[Dict[str, Any]], max_items: int = 7) -> List[str]:
    # Extract concrete medical gear terms from retrieved manual snippets.
    terms = [
        "Neck collar",
        "Suction",
        "Airway adjunct",
        "Portable oxygen",
        "Bag-valve mask",
        "Cervical collar",
        "Splint",
        "IV fluids",
        "Pulse oximeter",
        "Bandage",
        "Tourniquet",
        "Gloves",
    ]
    found: List[str] = []
    haystack = " ".join(str(src.get("snippet", "")) for src in rag_sources).lower()
    for term in terms:
        if term.lower() in haystack and term not in found:
            found.append(term)
    return found[:max_items]


def infer_hazard_from_context(final_text: str, rag_sources: List[Dict[str, Any]]) -> str:
    text = final_text or ""
    lowered = text.lower()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"hazard|risk|unstable|collapse|toxic|airway|bleed|evac", sentence, flags=re.I):
            return sentence.strip()
    snippet_blob = " ".join(str(src.get("snippet", "")) for src in rag_sources)
    for sentence in re.split(r"(?<=[.!?])\s+", snippet_blob):
        if re.search(r"hazard|risk|unstable|collapse|toxic|airway|bleed|evac", sentence, flags=re.I):
            return sentence.strip()
    if "critical" in lowered or "severe" in lowered:
        return "Elevated incident severity detected. Maintain controlled ingress and strict responder PPE discipline."
    return "Maintain scene control, verify responder PPE, and reassess hazards before patient movement."


def build_mission_payload(
    final_output: str,
    field_report: Dict[str, Any],
    protocol: Dict[str, Any],
    rag_sources: List[Dict[str, Any]],
    risk_score: float,
) -> Dict[str, Any]:
    field_payload = field_report.get("field_report", {}) if isinstance(field_report, dict) else {}
    protocol_payload = protocol.get("protocol", {}) if isinstance(protocol, dict) else {}

    priority = str(field_payload.get("priority_level") or protocol_payload.get("Priority") or "elevated").lower()
    supplies = field_payload.get("required_supplies") if isinstance(field_payload.get("required_supplies"), list) else []
    if not supplies:
        supplies = protocol_payload.get("Required_Gear") if isinstance(protocol_payload.get("Required_Gear"), list) else []
    if not supplies:
        supplies = infer_supplies_from_context(rag_sources)
    if not supplies:
        supplies = ["Protocol-specific supplies pending"]

    hazard = (
        field_payload.get("hazard_alert")
        or field_payload.get("responder_hazard_alert")
        or infer_hazard_from_context(final_output, rag_sources)
    )

    steps = protocol_payload.get("Action_Steps") if isinstance(protocol_payload.get("Action_Steps"), list) else []
    if not steps:
        steps = ["Stabilize scene", "Execute triage", "Coordinate evacuation"]

    significant = bool(
        risk_score > 0.35
        or priority in {"high", "critical", "immediate", "red"}
        or re.search(r"critical|severe|collapse|toxic|airway|hemorrhage|unstable", str(hazard), re.I)
    )

    return {
        "priority": priority,
        "supplies": [str(item) for item in supplies],
        "hazard": str(hazard),
        "steps": [str(step) for step in steps],
        "significant_hazard": significant,
    }


def _priority_badge(priority: str, risk_score: float) -> str:
    p = (priority or "").lower()
    if p in {"high", "critical", "immediate", "red"} or risk_score >= 0.45:
        return "<span class='priority-badge p-red'>PRIORITY RED</span>"
    if p in {"medium", "elevated", "yellow", "urgent"} or risk_score >= 0.2:
        return "<span class='priority-badge p-yellow'>PRIORITY YELLOW</span>"
    return "<span class='priority-badge p-green'>PRIORITY GREEN</span>"


def _render_directive_with_citations(final_output: str, rag_sources: List[Dict[str, Any]]) -> str:
    text = (final_output or "Awaiting triage directive...").strip()
    if not rag_sources:
        return _escape_html(text)

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        sentences = [_escape_html(text)]

    chunks: List[str] = []
    for idx, sentence in enumerate(sentences):
        source_idx = idx % max(1, len(rag_sources))
        src = rag_sources[source_idx]
        conf = confidence_pct(src.get("score", 1.0))
        tip = (
            f"<div class='cite-manual'>{_escape_html(str(src.get('manual_name', 'Manual')))} · p.{_escape_html(str(src.get('page', 'n/a')))}</div>"
            f"<div class='cite-confidence'>{conf:.1f}% Confidence</div>"
            f"<div class='cite-snippet'>{_escape_html(str(src.get('snippet', '')))}</div>"
        )
        chunks.append(
            f"{_escape_html(sentence)}"
            f"<details class='cite-pop'><summary class='cite-ref'>[i{source_idx + 1}]</summary><div class='cite-tip'>{tip}</div></details>"
        )
    return " ".join(chunks)


def render_output_console(
    final_output: str,
    tps: float,
    field_report: Dict[str, Any],
    protocol: Dict[str, Any],
    rag_sources: List[Dict[str, Any]],
    risk_score: float,
) -> None:
    mission = build_mission_payload(final_output, field_report or {}, protocol or {}, rag_sources or [], risk_score)
    priority_badge = _priority_badge(mission["priority"], risk_score)
    directive = _render_directive_with_citations(final_output, rag_sources or [])

    gear_chips = "".join(
        [
            (
                "<span class='gear-chip'>"
                "<span class='gear-icon'>[MED]</span>"
                f"<span>{_escape_html(item)}</span>"
                "</span>"
            )
            for item in mission["supplies"]
        ]
    )
    steps_html = "".join([f"<li>{_escape_html(step)}</li>" for step in mission["steps"]])
    warn_class = "hazard-critical" if mission["significant_hazard"] else "hazard-normal"
    source_cards = ""
    if rag_sources:
        source_cards = "".join([source_card_html(source) for source in rag_sources[:3]])

    st.markdown(
        "<section class='mission-card'>"
        "<div class='mission-top'>"
        "<div class='mission-title'>Mission Briefing</div>"
        "<div class='mission-badges'>"
        f"{priority_badge}"
        f"<span class='speed-badge'>{tps:.2f} tok/s</span>"
        "</div>"
        "</div>"
        "<div class='mission-label'>Live Directive</div>"
        f"<div class='directive-block'>{directive}</div>"
        "<div class='mission-grid'>"
        "<div class='mission-pane'>"
        "<div class='mission-label'>Gear Check</div>"
        f"<div class='gear-chips'>{gear_chips}</div>"
        "<div class='mission-label mission-label-gap'>Action Sequence</div>"
        f"<ol class='mission-steps'>{steps_html}</ol>"
        "</div>"
        "<div class='mission-pane'>"
        "<div class='mission-label'>Responder Hazard Alert</div>"
        f"<div class='hazard-box {warn_class}'>{_escape_html(mission['hazard'])}</div>"
        "</div>"
        "</div>"
        "<div class='report-stamp'>GROUNDED IN WHO PROTOCOL</div>"
        "</section>",
        unsafe_allow_html=True,
    )

    if source_cards:
        st.markdown(
            "<section class='sources-shell'>"
            "<div class='mission-label'>Grounded Source Register</div>"
            f"{source_cards}"
            "</section>",
            unsafe_allow_html=True,
        )


def render_field_report(report: Dict[str, Any], source: str) -> None:
    payload = report.get("field_report", {}) if isinstance(report, dict) else {}
    priority = str(payload.get("priority_level", "unknown")).upper()
    supplies = payload.get("required_supplies", [])
    hazard = payload.get("hazard_alert") or payload.get("responder_hazard_alert") or "Not specified"

    if not isinstance(supplies, list) or not supplies:
        supplies = ["No protocol-specific supplies extracted"]

    supplies_html = "".join([f"<li>{item}</li>" for item in supplies])
    st.markdown(
        "<div class='report-card field-report-card'>"
        "<div class='report-head'>Field Report Extraction</div>"
        f"<div class='report-meta'>Source: {source} | Priority: {priority}</div>"
        "<div class='report-label'>Required Supplies</div>"
        f"<ul>{supplies_html}</ul>"
        "<div class='report-label'>Responder Hazard Alert</div>"
        f"<div class='report-hazard'>{hazard}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_clipboard(protocol: Dict[str, Any], source: str) -> None:
    payload = protocol.get("protocol", {}) if isinstance(protocol, dict) else {}
    priority = payload.get("Priority", "UNKNOWN")
    steps = payload.get("Action_Steps", [])
    gear = payload.get("Required_Gear", [])

    steps_html = "".join([f"<li>{step}</li>" for step in steps]) if isinstance(steps, list) else "<li>Unavailable</li>"
    gear_html = "".join([f"<li>{item}</li>" for item in gear]) if isinstance(gear, list) else "<li>Unavailable</li>"

    st.markdown(
        "<div class='report-card'>"
        "<div class='report-head'>Digital Action Plan</div>"
        f"<div class='report-meta'>Source: {source} | Priority: {priority}</div>"
        "<div class='report-label'>Action Steps</div>"
        f"<ol>{steps_html}</ol>"
        "<div class='report-label'>Required Gear</div>"
        f"<ul>{gear_html}</ul>"
        "<div class='report-stamp'>GROUNDED IN WHO PROTOCOL</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def source_card_html(source: Dict[str, Any]) -> str:
    score = source.get("score", 1.0)
    badge = confidence_badge_html(score)
    meta = f"{source.get('manual_name', 'Manual')} · p.{source.get('page', 'n/a')}"
    return (
        "<div class='source-item'>"
        "<div class='source-row'>"
        "<span class='verify-badge'>Verified</span>"
        f"{badge}"
        f"<span class='source-meta'>{meta}</span>"
        "</div>"
        f"<div class='source-text'>{source.get('snippet', '')}</div>"
        "</div>"
    )


def execute_reasoning(
    engine: AuraEngine,
    strategic_mode: bool,
    prompt: str,
    trace_placeholder,
    console_placeholder,
) -> None:
    st.session_state.blocked = False
    st.session_state.blocked_code = ""
    st.session_state.latest_field_report = None
    st.session_state.latest_protocol = None
    st.session_state.rag_sources = []

    decision = engine.firewall.validate_intent(prompt)
    st.session_state.risk_score = float(getattr(decision, "score", 0.0) or 0.0)

    if not decision.allowed:
        st.session_state.blocked = True
        st.session_state.blocked_code = decision.violation_code or "FW_NEURAL_HIT"
        st.session_state.scan_active = False
        st.session_state.think_trace = "[Reasoning blocked by firewall]"
        st.session_state.final_output = decision.redirect_message or "Prompt blocked by firewall."
        trace_placeholder.markdown(
            process_trace_html(st.session_state.think_trace, 0.0, thinking=False),
            unsafe_allow_html=True,
        )
        console_placeholder.empty()
        with console_placeholder:
            render_output_console(
                st.session_state.final_output,
                0.0,
                st.session_state.latest_field_report or {},
                st.session_state.latest_protocol or {},
                st.session_state.rag_sources,
                float(st.session_state.get("risk_score", 0.0)),
            )
        return

    requested_model = engine.complex_model if strategic_mode else engine.fast_model
    st.session_state.last_model = engine.select_available_model(
        requested_model,
        fallbacks=[engine.fast_model, "gemma4:e2b"],
    )

    st.session_state.scan_active = True

    raw_last = ""
    think_last = ""
    final_last = ""
    tool_payload: Dict[str, Any] = {}

    start_ts = time.time()
    with st.status("Neural reasoning in progress...", expanded=False):
        for frame in engine.stream_triage_response(
            user_prompt=prompt,
            history=[],
            prefer_complex=strategic_mode,
        ):
            raw_last = frame.raw
            think_last = frame.think
            final_last = frame.final

            if frame.tool_payload:
                tool_payload = frame.tool_payload
            if frame.rag_sources:
                st.session_state.rag_sources = frame.rag_sources
            if frame.safety_violation_code:
                st.session_state.blocked = True
                st.session_state.blocked_code = frame.safety_violation_code

            elapsed = max(0.05, time.time() - start_ts)
            token_count = max(1, len((final_last or raw_last).split()))
            st.session_state.latest_tps = token_count / elapsed

            st.session_state.think_trace = clean_think_text(think_last)
            st.session_state.final_output = final_last

            trace_placeholder.markdown(
                process_trace_html(st.session_state.think_trace, st.session_state.latest_tps, thinking=True),
                unsafe_allow_html=True,
            )
            console_placeholder.empty()
            with console_placeholder:
                render_output_console(
                    st.session_state.final_output,
                    float(st.session_state.get("latest_tps", 0.0)),
                    st.session_state.latest_field_report or {},
                    st.session_state.latest_protocol or {},
                    st.session_state.rag_sources,
                    float(st.session_state.get("risk_score", 0.0)),
                )

    st.session_state.scan_active = False

    if tool_payload:
        st.session_state.latest_field_report = {
            "field_report": tool_payload,
            "source": "stream_tool_call",
        }
    else:
        st.session_state.latest_field_report = engine.request_medical_extraction(prompt)

    st.session_state.latest_protocol = engine.generate_rescue_protocol(prompt)

    trace_placeholder.markdown(
        process_trace_html(st.session_state.think_trace, st.session_state.latest_tps, thinking=False),
        unsafe_allow_html=True,
    )
    console_placeholder.empty()
    with console_placeholder:
        render_output_console(
            st.session_state.final_output,
            float(st.session_state.get("latest_tps", 0.0)),
            st.session_state.latest_field_report or {},
            st.session_state.latest_protocol or {},
            st.session_state.rag_sources,
            float(st.session_state.get("risk_score", 0.0)),
        )


def render_neural_hub(engine: AuraEngine) -> None:
    strategic_mode_default = bool(st.session_state.get("strategic_mode", False))
    st.markdown(
        "<div class='section-header center'>"
        "<div class='section-kicker'>Command</div>"
        "<div class='section-title'>Neural Command Hub</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    prompt = st.text_area(
        "Incident Command Prompt",
        key="incident_prompt",
        height=220,
        placeholder="Describe scenario, mission objective, constraints, and required output style.",
    )

    st.markdown(
        "<div class='toggle-intent'>"
        "Use Strategic Mode for complex, multi-step incidents that need deeper reasoning."
        "</div>",
        unsafe_allow_html=True,
    )
    toggle_left, toggle_mid, toggle_right = st.columns([1.2, 1.1, 1.2], gap="small")
    with toggle_mid:
        strategic_mode = st.toggle(
            "Strategic Mode",
            value=strategic_mode_default,
            key="strategic_mode",
            help="Enable heavier reasoning profile for complex operations.",
        )

    mode_class = "strategic-on" if strategic_mode else "strategic-off"
    st.markdown(f"<div class='hub-mode-indicator {mode_class}'></div>", unsafe_allow_html=True)

    run_button = st.button("Execute Tactical Triage", use_container_width=True, key="execute_triage")

    trace_placeholder = st.empty()
    console_placeholder = st.empty()

    if run_button and prompt.strip():
        execute_reasoning(engine, strategic_mode, prompt, trace_placeholder, console_placeholder)
    else:
        trace_placeholder.markdown(
            process_trace_html(
                st.session_state.get("think_trace", ""),
                float(st.session_state.get("latest_tps", 0.0)),
                thinking=bool(st.session_state.get("scan_active", False)),
            ),
            unsafe_allow_html=True,
        )
        with console_placeholder:
            render_output_console(
                st.session_state.get("final_output", ""),
                float(st.session_state.get("latest_tps", 0.0)),
                st.session_state.get("latest_field_report") or {},
                st.session_state.get("latest_protocol") or {},
                st.session_state.get("rag_sources", []),
                float(st.session_state.get("risk_score", 0.0)),
            )




def main() -> None:
    st.set_page_config(page_title="Aura-G4 Tactical Command Center", layout="wide")
    load_css()
    init_state()

    engine: AuraEngine = st.session_state.engine
    engine.fast_model = engine.select_available_model("gemma4:e4b", fallbacks=["gemma4:e2b"])
    engine.complex_model = engine.select_available_model("gemma4:e2b", fallbacks=[engine.fast_model])

    manuals = engine.list_loaded_manuals()

    render_header(engine, manuals)
    render_sidebar_monitor(engine, manuals)

    left_col, right_col = st.columns([1, 1.8], gap="large")

    with left_col:
        render_field_intelligence(engine)

    with right_col:
        render_neural_hub(engine)

    render_footer()


def render_footer() -> None:
    utc_now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    model = str(st.session_state.get("last_model", "n/a")).upper()
    st.markdown(
        "<div class='footer-dock'>"
        "<footer class='footer-shell'>"
        "<div class='footer-line'><span class='system-name-inline'>AURA-G4</span> Tactical Command Stack</div>"
        "<div class='footer-pills'>"
        f"<span>MODEL {model}</span>"
        f"<span>SYNC {utc_now}</span>"
        "</div>"
        "<div class='footer-meta'>Local inference with grounded protocol retrieval</div>"
        "</footer>"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
