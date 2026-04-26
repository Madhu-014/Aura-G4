"use client";

import { motion, useAnimationControls } from "framer-motion";
import { Activity, BrainCircuit, Cpu, Maximize2, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ActionClipboard } from "@/components/ActionClipboard";
import { ProcessTrace } from "@/components/ProcessTrace";
import { Card } from "@/components/ui/card";
import { useSystemStore } from "@/lib/store";
import type { ManualsResponse, StreamFrame, Telemetry, ValidateResponse } from "@/lib/types";
import styles from "@/app/page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

type RagSource = {
  manual_name: string;
  page: number;
  score: number;
  snippet: string;
};

type VisionCard = {
  title: string;
  body: string;
};

type ExpandedPanel = "vision" | "hazard" | "sources" | "command" | "trace" | "clipboard";

function Meter({ label, value, suffix = "%" }: { label: string; value: number; suffix?: string }) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div className={styles.meterRow}>
      <div className={styles.meterMeta}>
        <span>{label}</span>
        <span>
          {bounded.toFixed(1)}
          {suffix}
        </span>
      </div>
      <div className={styles.meterTrack}>
        <span className={styles.meterFill} style={{ width: `${bounded}%` }} />
      </div>
    </div>
  );
}

function sanitizeTacticalText(text: string) {
  if (!text) {
    return "";
  }
  return text.replace(/rag_context_unavailable/gi, "Awaiting local manual retrieval...");
}

function normalizeRagSources(items: Array<Record<string, unknown>>): RagSource[] {
  return items
    .map((item) => ({
      manual_name: typeof item.manual_name === "string" ? item.manual_name : "Unknown Manual",
      page: typeof item.page === "number" ? item.page : 0,
      score: typeof item.score === "number" ? item.score : 0,
      snippet: typeof item.snippet === "string" ? item.snippet : "",
    }))
    .slice(0, 10);
}

function parseVisionCards(summary: string): VisionCard[] {
  const clean = sanitizeTacticalText(summary).trim();
  if (!clean) {
    return [];
  }

  const chunks = clean.split(/\n(?=###\s+)/g);
  const cards: VisionCard[] = [];

  for (const chunk of chunks) {
    const trimmed = chunk.trim();
    if (!trimmed) {
      continue;
    }

    const headingMatch = trimmed.match(/^###\s+([^\n]+)\n?([\s\S]*)$/);
    if (headingMatch) {
      cards.push({
        title: headingMatch[1].trim(),
        body: headingMatch[2].trim() || "Awaiting detailed hazard extraction.",
      });
      continue;
    }

    cards.push({
      title: cards.length === 0 ? "Situation Overview" : `Assessment ${cards.length + 1}`,
      body: trimmed,
    });
  }

  if (cards.length) {
    return cards.slice(0, 6);
  }

  return [
    {
      title: "Situation Overview",
      body: clean,
    },
  ];
}

export default function HomePage() {
  const { telemetry, model, tacticalOverride, violationMessage, setTelemetry, setValidation, setOverride } =
    useSystemStore();

  const [prompt, setPrompt] = useState("");
  const [trace, setTrace] = useState("");
  const [answer, setAnswer] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [visionStreaming, setVisionStreaming] = useState(false);
  const [visionPrompt, setVisionPrompt] = useState<string>("Extract tactical hazards and responder ingress path.");
  const [visionSummary, setVisionSummary] = useState("");
  const [visionFile, setVisionFile] = useState<File | null>(null);
  const [manuals, setManuals] = useState<string[]>([]);
  const [ragSources, setRagSources] = useState<RagSource[]>([]);
  const [hubFlash, setHubFlash] = useState(false);
  const [expandedPanel, setExpandedPanel] = useState<ExpandedPanel | null>(null);
  const hubControls = useAnimationControls();

  useEffect(() => {
    let mounted = true;

    async function pollTelemetry() {
      try {
        const response = await fetch(`${API_BASE}/api/telemetry`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error("telemetry unavailable");
        }
        const data = (await response.json()) as Telemetry;
        if (mounted) {
          setTelemetry(data);
        }
      } catch {
        if (mounted) {
          setOverride(false);
        }
      }
    }

    pollTelemetry();
    const timer = setInterval(pollTelemetry, 2000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [setOverride, setTelemetry]);

  useEffect(() => {
    let mounted = true;

    async function fetchManuals() {
      try {
        const response = await fetch(`${API_BASE}/api/manuals`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error("manual table unavailable");
        }
        const data = (await response.json()) as ManualsResponse;
        if (mounted && Array.isArray(data.manuals)) {
          setManuals(data.manuals);
        }
      } catch {
        if (mounted) {
          setManuals((current) => current);
        }
      }
    }

    fetchManuals();
    const timer = setInterval(fetchManuals, 15000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!manuals.length && ragSources.length) {
      const inferred = Array.from(new Set(ragSources.map((item) => item.manual_name))).filter(Boolean);
      if (inferred.length) {
        setManuals(inferred);
      }
    }
  }, [manuals.length, ragSources]);

  async function runTriage() {
    if (!prompt.trim() || streaming) {
      return;
    }
    setTrace("");
    setAnswer("");
    setRagSources([]);

    try {
      const validateRes = await fetch(`${API_BASE}/api/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      const validation = (await validateRes.json()) as ValidateResponse;
      setValidation(validation);

      if (!validation.allowed) {
        setOverride(true, validation.redirect_message || validation.reason);
        return;
      }

      setOverride(false, "");

      // Only show inference activation after firewall validation passes.
      setHubFlash(true);
      hubControls.start({
        x: [0, -3, 3, -2, 2, 0],
        transition: { duration: 0.28, ease: "easeInOut" },
      });
      window.setTimeout(() => setHubFlash(false), 360);

      setStreaming(true);

      const streamRes = await fetch(`${API_BASE}/api/triage/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, prefer_complex: false }),
      });

      if (!streamRes.ok || !streamRes.body) {
        throw new Error("stream unavailable");
      }

      const reader = streamRes.body.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        sseBuffer += decoder.decode(value, { stream: true });
        const events = sseBuffer.split("\n\n");
        sseBuffer = events.pop() ?? "";

        for (const evt of events) {
          const line = evt
            .split("\n")
            .find((entry) => entry.startsWith("data: "))
            ?.replace("data: ", "");
          if (!line) {
            continue;
          }

          const frame = JSON.parse(line) as StreamFrame;
          if (frame.error) {
            throw new Error(frame.error);
          }
          if (frame.think !== undefined) {
            setTrace(sanitizeTacticalText(frame.think));
          }
          if (frame.final !== undefined) {
            setAnswer(sanitizeTacticalText(frame.final));
          }
          if (Array.isArray(frame.rag_sources) && frame.rag_sources.length > 0) {
            setRagSources(normalizeRagSources(frame.rag_sources));
          }
          if (frame.was_intercepted) {
            setOverride(true, frame.safety_violation_code || "Semantic firewall interruption.");
          }
        }
      }
    } catch (error) {
      setOverride(true, error instanceof Error ? error.message : "Tactical stream failed.");
    } finally {
      setStreaming(false);
    }
  }

  async function runVision() {
    if (!visionFile || visionStreaming) {
      return;
    }

    setVisionStreaming(true);

    try {
      const form = new FormData();
      form.append("file", visionFile);
      form.append("prompt", visionPrompt || "Analyze hazards and extraction approach.");

      const response = await fetch(`${API_BASE}/api/vision`, {
        method: "POST",
        body: form,
      });

      if (!response.ok) {
        setVisionSummary("Vision extraction failed.");
        return;
      }

      const payload = (await response.json()) as { final?: string };
      setVisionSummary(sanitizeTacticalText(payload.final || "No vision output returned."));
    } catch {
      setVisionSummary("Vision extraction failed.");
    } finally {
      setVisionStreaming(false);
    }
  }

  const npuActive =
    streaming || visionStreaming || telemetry?.npu_heartbeat === "ACTIVE" || telemetry?.npu_heartbeat === "WARM";

  const hazardCards = parseVisionCards(visionSummary);
  const inferenceSpeed = telemetry?.tokens_per_second ?? 0;
  const manualRows = manuals.slice(0, 10);
  const firewallLoaded = Boolean(telemetry?.firewall_status?.model_loaded);
  const firewallBackend = String(telemetry?.firewall_status?.backend ?? "unknown").replace(/_/g, " ").toUpperCase();
  const firewallDevice = String(telemetry?.firewall_status?.device ?? "cpu").toUpperCase();

  const expandedPanelNode =
    expandedPanel === null ? null : (
      <div className={styles.panelModalBackdrop} onClick={() => setExpandedPanel(null)}>
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 8 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className={styles.panelModal}
          onClick={(event) => event.stopPropagation()}
        >
          <div className={styles.panelModalTopBar}>
            <div>
              <div className={styles.panelModalKicker}>Expanded Tactical View</div>
              <div className={styles.panelModalTitle}>
                {expandedPanel === "vision"
                  ? "Vision Intake"
                  : expandedPanel === "hazard"
                    ? "Visual Hazard Assessment"
                    : expandedPanel === "sources"
                      ? "RAG Source Feed"
                      : expandedPanel === "command"
                        ? "Incident Prompt Console"
                        : expandedPanel === "trace"
                          ? "Process Trace"
                          : "Digital Action Plan"}
              </div>
            </div>
            <button type="button" className={styles.panelModalClose} onClick={() => setExpandedPanel(null)} aria-label="Close expanded card">
              <X size={16} />
            </button>
          </div>

          <div className={styles.panelModalBody}>
            {expandedPanel === "vision" ? (
              <Card className={`${styles.glass} ${styles.panelCard} ${styles.expandedPanelCard}`}>
                <div className={styles.panelHead}>
                  <h3 className={styles.titleXs}>Vision Intake</h3>
                  <span className={styles.panelTag}>{visionStreaming ? "Vision Live" : "Field Upload"}</span>
                </div>
                <div className={styles.fieldStack}>
                  <div className={styles.promptBlock}>
                    <label className={styles.promptLabel} htmlFor="vision-image-input-expanded">
                      Image Upload
                    </label>
                    <p className={styles.promptHint}>Choose a field image, then add the analysis prompt below.</p>
                  </div>
                  <input
                    id="vision-image-input-expanded"
                    type="file"
                    accept="image/*"
                    onChange={(e) => setVisionFile(e.target.files?.[0] ?? null)}
                    className={styles.uploadInput}
                  />
                  <div className={styles.promptBlock}>
                    <label className={styles.promptLabel} htmlFor="vision-prompt-input-expanded">
                      Vision Prompt
                    </label>
                    <p className={styles.promptHint}>Ask for hazards, ingress, casualties, or any mixed image + text analysis.</p>
                  </div>
                  <textarea
                    id="vision-prompt-input-expanded"
                    value={visionPrompt ?? ""}
                    onChange={(e) => setVisionPrompt(e.target.value)}
                    rows={8}
                    className={styles.promptInput}
                    placeholder="Assess responder hazards and safest ingress route..."
                  />
                  <button
                    type="button"
                    onClick={runVision}
                    disabled={visionStreaming || !visionFile}
                    className={`${styles.actionBtn} border border-[#0070f3]/45 bg-[#0070f3]/15 text-[#b8d6ff] hover:shadow-[0_0_16px_rgba(0,112,243,0.22)]`}
                  >
                    {visionStreaming ? "Analyzing Image" : "Analyze Field Image"}
                  </button>
                </div>
              </Card>
            ) : expandedPanel === "hazard" ? (
              <Card className={`${styles.glass} ${styles.panelCard} ${styles.expandedPanelCard}`}>
                <div className={styles.panelHead}>
                  <h3 className={styles.titleXs}>Visual Hazard Assessment</h3>
                  <span className={styles.panelTag}>Responder View</span>
                </div>
                <div className={styles.expandedScrollArea}>
                  <div className={styles.hazardGrid}>
                    {hazardCards.length > 0 ? (
                      hazardCards.map((card, index) => (
                        <article key={`${card.title}-${index}`} className={styles.hazardCard}>
                          <h4 className={styles.hazardTitle}>{card.title}</h4>
                          <p className={styles.hazardBody}>{card.body}</p>
                        </article>
                      ))
                    ) : (
                      <article className={styles.hazardCard}>
                        <h4 className={styles.hazardTitle}>Awaiting Vision Analysis</h4>
                        <p className={styles.hazardBody}>
                          Upload an incident image to generate structured hazard cards and safe ingress guidance.
                        </p>
                      </article>
                    )}
                  </div>
                </div>
              </Card>
            ) : expandedPanel === "sources" ? (
              <Card className={`${styles.glass} ${styles.panelCard} ${styles.expandedPanelCard}`}>
                <div className={styles.panelHead}>
                  <h3 className={styles.titleXs}>RAG Source Feed</h3>
                  <span className={styles.panelTag}>Scrollable</span>
                </div>
                <div className={styles.expandedScrollArea}>
                  <div className={styles.sourcesList}>
                    {ragSources.length > 0 ? (
                      ragSources.map((source, index) => (
                        <article key={`${source.manual_name}-${source.page}-${index}`} className={styles.sourceItem}>
                          <div className={styles.sourceMeta}>
                            <strong>{source.manual_name}</strong>
                            <span>
                              Page {source.page || 0} | Score {(source.score * 100).toFixed(1)}%
                            </span>
                          </div>
                          <p className={styles.sourceSnippet}>{source.snippet || "No snippet available."}</p>
                        </article>
                      ))
                    ) : (
                      <article className={styles.sourceItem}>
                        <div className={styles.sourceMeta}>
                          <strong>Source Buffer Empty</strong>
                          <span>Run triage to populate manual citations.</span>
                        </div>
                      </article>
                    )}
                  </div>
                </div>
              </Card>
            ) : expandedPanel === "command" ? (
              <Card className={`${styles.glass} ${styles.panelCard} ${styles.commandCard} ${styles.expandedPanelCard}`}>
                <div className={styles.panelHead}>
                  <h3 className={styles.titleXs}>Incident Prompt Console</h3>
                  <span className={styles.panelTag}>{streaming ? "Inference Live" : "Ready"}</span>
                </div>
                <div className={styles.promptBlock}>
                  <label className={styles.promptLabel} htmlFor="triage-command-input-expanded">
                    Mission Prompt
                  </label>
                  <p className={styles.promptHint}>
                    Include threat profile, operational constraints, and expected triage format.
                  </p>
                </div>
                <textarea
                  id="triage-command-input-expanded"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Example: Building collapse with airway compromise, 4 casualties, low visibility. Provide ETAT sequence and extraction priorities."
                  className={styles.commandInput}
                />
                <div className={styles.commandActionRow}>
                  <button type="button" onClick={runTriage} disabled={streaming} className={styles.executeBtn}>
                    {streaming ? "Streaming Response" : "Run Triage"}
                  </button>
                  <div className={styles.executeMeta}>
                    {streaming
                      ? "Neural reasoning active. Firewall semantic guard engaged."
                      : "Standby. Prompt will be validated by DeBERTa firewall before inference."}
                  </div>
                </div>
              </Card>
            ) : expandedPanel === "trace" ? (
              <div className={styles.expandedComponentShell}>
                <ProcessTrace thinkTrace={trace} streaming={streaming} />
              </div>
            ) : (
              <div className={styles.expandedComponentShell}>
                <ActionClipboard content={answer} />
              </div>
            )}
          </div>
        </motion.div>
      </div>
    );

  return (
    <main className={`relative h-screen overflow-hidden bg-tactical-bg px-3 py-3 text-white md:px-5 ${styles.viewport}`}>
      <div className="pointer-events-none absolute inset-0 bg-grid bg-[size:52px_52px] opacity-20" />
      <div className="pointer-events-none absolute -left-20 top-6 h-[28rem] w-[28rem] rounded-full bg-[#0b3c74]/30 blur-[110px]" />
      <div className="pointer-events-none absolute left-[30%] top-[-8%] h-[18rem] w-[24rem] rounded-full bg-white/10 blur-[120px]" />
      <div className="pointer-events-none absolute -right-20 bottom-[-5%] h-[24rem] w-[30rem] rounded-full bg-[#00FF41]/12 blur-[120px]" />

      {tacticalOverride && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#120000]/85 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="tactical-override w-full max-w-lg rounded-2xl border border-[#ff2d2d]/80 bg-black/85 p-6"
          >
            <div className="mb-2 flex items-center gap-2 text-[#ff5f5f]">
              <ShieldAlert className="h-5 w-5" />
              <span className="text-xs uppercase tracking-[0.25em]">Tactical Override</span>
            </div>
            <h2 className="mb-3 text-xl font-semibold">Security Violation Detected</h2>
            <p className="text-sm text-white/85">{violationMessage || "Firewall blocked operation."}</p>
          </motion.div>
        </div>
      )}

      <div className={`${styles.appShell} mx-auto h-full w-full max-w-[1880px]`}>
        <aside className={styles.sidebar}>
          <Card className={`${styles.glass} ${styles.sidebarCard}`}>
            <div className={styles.sidebarHeader}>
              <div>
                <div className={styles.sidebarKicker}>Monitor</div>
                <h2 className={styles.sidebarTitle}>Aura Tactical Monitor</h2>
              </div>
              <div className={styles.sidebarStatus}>
                <span
                  className={`${styles.heartbeatDot} ${npuActive ? styles.heartbeatThinking : styles.heartbeatStandby}`}
                  aria-hidden="true"
                />
                {telemetry ? (npuActive ? "ACTIVE" : "STANDBY") : "OFFLINE"}
              </div>
            </div>

            <div className={styles.sidebarScroll}>
              <section className={styles.monitorSection}>
                <h3 className={styles.sectionTitle}>Device Metrics</h3>
                <div className={styles.meterStack}>
                  <Meter label="CPU" value={telemetry?.cpu_percent ?? 0} />
                  <Meter label="RAM" value={telemetry?.ram_percent ?? 0} />
                  <Meter label="VRAM" value={Math.min(100, (telemetry?.mps_allocated_mb ?? 0) / 100)} />
                </div>
              </section>

              <section className={styles.monitorSection}>
                <h3 className={styles.sectionTitle}>Accelerator Status</h3>
                <div className={styles.accelList}>
                  <div className={styles.accelRow}>
                    <span className={styles.accelLabel}>M2/NPU</span>
                    <span className={styles.accelValue}>{telemetry?.npu_heartbeat ?? "IDLE"}</span>
                  </div>
                  <div className={styles.accelRow}>
                    <span className={styles.accelLabel}>Active Model</span>
                    <span className={styles.accelValue}>{model}</span>
                  </div>
                  <div className={styles.accelRow}>
                    <span className={styles.accelLabel}>Inference</span>
                    <span className={styles.accelValue}>{inferenceSpeed.toFixed(1)} tok/s</span>
                  </div>
                </div>
              </section>

              <section className={styles.monitorSection}>
                <h3 className={styles.sectionTitle}>Firewall Runtime</h3>
                <div className={styles.accelList}>
                  <div className={styles.accelRow}>
                    <span className={styles.accelLabel}>Guard</span>
                    <span className={styles.accelValue}>{firewallLoaded ? "ACTIVE" : "STANDBY"}</span>
                  </div>
                  <div className={styles.accelRow}>
                    <span className={styles.accelLabel}>Backend</span>
                    <span className={styles.accelValue}>{firewallBackend}</span>
                  </div>
                  <div className={styles.accelRow}>
                    <span className={styles.accelLabel}>Device</span>
                    <span className={styles.accelValue}>{firewallDevice}</span>
                  </div>
                </div>
              </section>

              <section className={styles.monitorSection}>
                <h3 className={styles.sectionTitle}>Aura Knowledge Base</h3>
                <div className={styles.knowledgeTableWrap}>
                  <table className={styles.knowledgeTable}>
                    <thead>
                      <tr>
                        <th>PDF</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {manualRows.length > 0 ? (
                        manualRows.map((manual) => (
                          <tr key={manual}>
                            <td title={manual}>{manual}</td>
                            <td>Indexed</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={2}>Awaiting indexed manuals...</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </Card>
        </aside>

        <section className={styles.workspace}>
          <motion.header
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className={`${styles.glass} ${styles.workspaceHeader}`}
          >
            <div className={styles.workspaceHeadLeft}>
              <div className={styles.workspaceKicker}>Neural Stage</div>
              <h1 className={styles.workspaceTitle}>Aura-G4 Bilateral Tactical Hub</h1>
              <p className={styles.workspaceSub}>
                Field-first analysis on the left, mission command synthesis on the right.
              </p>
            </div>
            <div className={styles.workspaceHeadRight}>
              <span className={styles.speedBadge}>Inference Speed: {inferenceSpeed.toFixed(1)} tok/s</span>
              <span className={styles.workspaceBadge}>Local Inference</span>
            </div>
          </motion.header>

          <div className={styles.bilateralGrid}>
            <section className={styles.fieldIntel}>
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                <Card className={`${styles.glass} ${styles.panelCard}`}>
                  <div className={styles.panelHead}>
                    <h3 className={styles.titleXs}>Vision Intake</h3>
                    <div className={styles.panelHeadActions}>
                      <span className={styles.panelTag}>{visionStreaming ? "Vision Live" : "Field Upload"}</span>
                      <button type="button" className={styles.expandBtn} onClick={() => setExpandedPanel("vision")} aria-label="Expand Vision Intake card">
                        <Maximize2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className={styles.fieldStack}>
                    <div className={styles.promptBlock}>
                      <label className={styles.promptLabel} htmlFor="vision-image-input">
                        Image Upload
                      </label>
                      <p className={styles.promptHint}>Choose a field image, then add the analysis prompt below.</p>
                    </div>
                    <input
                      id="vision-image-input"
                      type="file"
                      accept="image/*"
                      onChange={(e) => setVisionFile(e.target.files?.[0] ?? null)}
                      className={styles.uploadInput}
                    />
                    <div className={styles.promptBlock}>
                      <label className={styles.promptLabel} htmlFor="vision-prompt-input">
                        Vision Prompt
                      </label>
                      <p className={styles.promptHint}>Ask for hazards, ingress, casualties, or any mixed image + text analysis.</p>
                    </div>
                    <textarea
                      id="vision-prompt-input"
                      value={visionPrompt ?? ""}
                      onChange={(e) => setVisionPrompt(e.target.value)}
                      rows={3}
                      className={styles.promptInput}
                      placeholder="Assess responder hazards and safest ingress route..."
                    />
                    <button
                      type="button"
                      onClick={runVision}
                      disabled={visionStreaming || !visionFile}
                      className={`${styles.actionBtn} border border-[#0070f3]/45 bg-[#0070f3]/15 text-[#b8d6ff] hover:shadow-[0_0_16px_rgba(0,112,243,0.22)]`}
                    >
                      {visionStreaming ? "Analyzing Image" : "Analyze Field Image"}
                    </button>
                  </div>
                </Card>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 }}>
                <Card className={`${styles.glass} ${styles.panelCard} ${styles.hazardCardWrap}`}>
                  <div className={styles.panelHead}>
                    <h3 className={styles.titleXs}>Visual Hazard Assessment</h3>
                    <div className={styles.panelHeadActions}>
                      <span className={styles.panelTag}>Responder View</span>
                      <button type="button" className={styles.expandBtn} onClick={() => setExpandedPanel("hazard")} aria-label="Expand Visual Hazard Assessment card">
                        <Maximize2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className={styles.hazardGrid}>
                    {hazardCards.length > 0 ? (
                      hazardCards.map((card, index) => (
                        <article key={`${card.title}-${index}`} className={styles.hazardCard}>
                          <h4 className={styles.hazardTitle}>{card.title}</h4>
                          <p className={styles.hazardBody}>{card.body}</p>
                        </article>
                      ))
                    ) : (
                      <article className={styles.hazardCard}>
                        <h4 className={styles.hazardTitle}>Awaiting Vision Analysis</h4>
                        <p className={styles.hazardBody}>
                          Upload an incident image to generate structured hazard cards and safe ingress guidance.
                        </p>
                      </article>
                    )}
                  </div>
                </Card>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
                <Card className={`${styles.glass} ${styles.panelCard} ${styles.sourceFeed}`}>
                  <div className={styles.panelHead}>
                    <h3 className={styles.titleXs}>RAG Source Feed</h3>
                    <div className={styles.panelHeadActions}>
                      <span className={styles.panelTag}>Scrollable</span>
                      <button type="button" className={styles.expandBtn} onClick={() => setExpandedPanel("sources")} aria-label="Expand RAG Source Feed card">
                        <Maximize2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className={styles.sourcesList}>
                    {ragSources.length > 0 ? (
                      ragSources.map((source, index) => (
                        <article key={`${source.manual_name}-${source.page}-${index}`} className={styles.sourceItem}>
                          <div className={styles.sourceMeta}>
                            <strong>{source.manual_name}</strong>
                            <span>
                              Page {source.page || 0} | Score {(source.score * 100).toFixed(1)}%
                            </span>
                          </div>
                          <p className={styles.sourceSnippet}>{source.snippet || "No snippet available."}</p>
                        </article>
                      ))
                    ) : (
                      <article className={styles.sourceItem}>
                        <div className={styles.sourceMeta}>
                          <strong>Source Buffer Empty</strong>
                          <span>Run triage to populate manual citations.</span>
                        </div>
                      </article>
                    )}
                  </div>
                </Card>
              </motion.div>
            </section>

            <section className={styles.neuralHub}>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <Card className={`${styles.glass} ${styles.panelCard} ${styles.commandCard} ${hubFlash ? styles.hubFlash : ""}`}>
                  <div className={styles.panelHead}>
                    <h3 className={styles.titleXs}>Incident Prompt Console</h3>
                    <div className={styles.panelHeadActions}>
                      <span className={styles.panelTag}>{streaming ? "Inference Live" : "Ready"}</span>
                      <button type="button" className={styles.expandBtn} onClick={() => setExpandedPanel("command")} aria-label="Expand Incident Prompt Console card">
                        <Maximize2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className={styles.promptBlock}>
                    <label className={styles.promptLabel} htmlFor="triage-command-input">
                      Mission Prompt
                    </label>
                    <p className={styles.promptHint}>
                      Include threat profile, operational constraints, and expected triage format.
                    </p>
                  </div>
                  <textarea
                    id="triage-command-input"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Example: Building collapse with airway compromise, 4 casualties, low visibility. Provide ETAT sequence and extraction priorities."
                    className={styles.commandInput}
                  />
                  <div className={styles.commandActionRow}>
                    <button type="button" onClick={runTriage} disabled={streaming} className={styles.executeBtn}>
                      {streaming ? "Streaming Response" : "Run Triage"}
                    </button>
                    <div className={styles.executeMeta}>
                      {streaming
                        ? "Neural reasoning active. Firewall semantic guard engaged."
                        : "Standby. Prompt will be validated by DeBERTa firewall before inference."}
                    </div>
                  </div>
                </Card>
              </motion.div>

              <div className={styles.hubOutputs}>
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: 0.08 }}
                  className={styles.traceWrap}
                >
                  <div className={styles.cardWithExpand}>
                    <button type="button" className={styles.expandFloatingBtn} onClick={() => setExpandedPanel("trace")} aria-label="Expand Process Trace card">
                      <Maximize2 size={14} />
                    </button>
                    <ProcessTrace thinkTrace={trace} streaming={streaming} />
                  </div>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: 0.12 }}
                  className={styles.planWrap}
                >
                  <div className={styles.cardWithExpand}>
                    <button type="button" className={styles.expandFloatingBtn} onClick={() => setExpandedPanel("clipboard")} aria-label="Expand Digital Action Plan card">
                      <Maximize2 size={14} />
                    </button>
                    <ActionClipboard content={answer} />
                  </div>
                </motion.div>
              </div>
            </section>
          </div>
        </section>
      </div>
      {expandedPanelNode}
    </main>
  );
}
