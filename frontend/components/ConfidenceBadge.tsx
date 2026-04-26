"use client";

import { CheckCircle2 } from "lucide-react";

import styles from "@/components/ConfidenceBadge.module.css";

type ConfidenceBadgeProps = {
  score: number;
};

export function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  const confidence = Math.max(0, Math.min(100, (1 - score) * 100));
  const tone = confidence > 90 ? styles.high : confidence >= 75 ? styles.mid : styles.low;

  return (
    <span className={`${styles.badge} ${tone}`}>
      <CheckCircle2 size={13} />
      Verified {confidence.toFixed(1)}%
    </span>
  );
}
