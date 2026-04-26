export type ValidateResponse = {
  allowed: boolean;
  reason: string;
  score: number;
  violation_code?: string | null;
  redirect_message?: string | null;
};

export type Telemetry = {
  cpu_percent: number;
  ram_percent: number;
  mps_allocated_mb: number;
  npu_heartbeat: string;
  tokens_per_second: number;
  active_model: string;
  firewall_status: {
    model_loaded: boolean;
    backend: string;
    device: string;
    last_validation_ts: number;
    last_decision_reason: string;
  };
};

export type StreamFrame = {
  delta?: string;
  raw?: string;
  think?: string;
  final?: string;
  was_intercepted?: boolean;
  safety_violation_code?: string | null;
  rag_sources?: Array<Record<string, unknown>>;
  error?: string;
  done?: boolean;
  tokens_per_second?: number;
};

export type ManualsResponse = {
  manuals: string[];
};
