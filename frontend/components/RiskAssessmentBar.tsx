"use client";

import { Card } from "@/components/ui/card";

type RiskAssessmentBarProps = {
  score: number;
};

export function RiskAssessmentBar({ score }: RiskAssessmentBarProps) {
  const pct = Math.max(0, Math.min(100, score * 100));
  const tier = pct < 35 ? "LOW" : pct < 70 ? "ELEVATED" : "HIGH";
  const tierTone = pct < 35 ? "text-[#8fffc2]" : pct < 70 ? "text-[#ffd166]" : "text-[#ff8e8e]";

  return (
    <Card className="bg-slate-900/40 p-4 backdrop-blur-xl border border-emerald-500/20 shadow-[0_0_15px_rgba(0,255,65,0.05)]">
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.2em] text-white/70">
        <span>Firewall Risk</span>
        <span className={tierTone}>
          {pct.toFixed(1)}% {tier}
        </span>
      </div>
      <div className="h-3 overflow-hidden rounded-full border border-white/20 bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#00FF41] via-[#ffdb4d] to-[#ff2d2d] transition-all duration-500 shadow-[0_0_14px_rgba(0,255,65,0.25)]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </Card>
  );
}
