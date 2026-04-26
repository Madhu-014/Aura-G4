import { create } from "zustand";

import type { Telemetry, ValidateResponse } from "@/lib/types";

type SystemState = {
  telemetry: Telemetry | null;
  riskScore: number;
  online: boolean;
  tacticalOverride: boolean;
  violationMessage: string;
  model: string;
  setTelemetry: (telemetry: Telemetry) => void;
  setValidation: (validation: ValidateResponse) => void;
  setOverride: (enabled: boolean, message?: string) => void;
};

export const useSystemStore = create<SystemState>((set) => ({
  telemetry: null,
  riskScore: 0,
  online: false,
  tacticalOverride: false,
  violationMessage: "",
  model: "gemma4:e4b",
  setTelemetry: (telemetry) =>
    set({
      telemetry,
      online: true,
      model: telemetry.active_model,
    }),
  setValidation: (validation) =>
    set({
      riskScore: validation.score ?? 0,
      tacticalOverride: !validation.allowed,
      violationMessage:
        validation.redirect_message ||
        validation.reason ||
        "Security policy rejected this request.",
    }),
  setOverride: (enabled, message = "") =>
    set({ tacticalOverride: enabled, violationMessage: message }),
}));
