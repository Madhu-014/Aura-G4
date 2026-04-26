"use client";

import { BadgeCheck } from "lucide-react";

import { Card } from "@/components/ui/card";
import styles from "@/components/ActionClipboard.module.css";

type ActionClipboardProps = {
  content: string;
};

export function ActionClipboard({ content }: ActionClipboardProps) {
  const bodyText = content || "Awaiting response from tactical AI engine.";
  const isWaiting = !content;

  return (
    <Card className={`${styles.shell} bg-slate-900/40 p-5 backdrop-blur-xl border border-emerald-500/20 shadow-[0_0_15px_rgba(0,255,65,0.05)]`}>
      <div className={styles.headRow}>
        <h3 className="text-sm uppercase tracking-[0.25em] text-white/85">Digital Action Plan</h3>
        <span className={styles.verifiedPill}>
          <BadgeCheck size={12} /> WHO ETAT Verified
        </span>
      </div>

      <div className={styles.badgeRow}>
        <span className={styles.statusTag}>Protocol Aligned</span>
      </div>

      <div className={styles.board}>
        <div className={styles.labelRow}>
          <div className={styles.label}>Tactical Clipboard</div>
          <div className={styles.subLabel}>Protocol-Synchronized</div>
        </div>
        <div className={`${styles.body} ${isWaiting ? styles.bodyMuted : ""}`}>{bodyText}</div>
        <span className={styles.seal}>[GROUNDED IN WHO PROTOCOL]</span>
      </div>
    </Card>
  );
}
