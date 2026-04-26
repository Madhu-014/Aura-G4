"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import styles from "@/components/ProcessTrace.module.css";

type ProcessTraceProps = {
  thinkTrace: string;
  streaming: boolean;
};

export function ProcessTrace({ thinkTrace, streaming }: ProcessTraceProps) {
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (!thinkTrace) {
      setTyped("");
      return;
    }

    let frame = 0;
    const speed = streaming ? 2 : 4;
    const interval = window.setInterval(() => {
      frame += speed;
      setTyped(thinkTrace.slice(0, frame));
      if (frame >= thinkTrace.length) {
        window.clearInterval(interval);
      }
    }, 14);

    return () => window.clearInterval(interval);
  }, [thinkTrace, streaming]);

  const displayText = typed || "<|think|> awaiting tactical stream...";

  return (
    <Card className={`${styles.shell} bg-slate-900/40 p-4 backdrop-blur-xl border border-emerald-500/20 shadow-[0_0_15px_rgba(0,255,65,0.05)]`}>
      <div className={styles.headRow}>
        <span className={styles.title}>Process Trace</span>
        <span className={styles.status}>
          <span className={`${styles.dot} ${streaming ? styles.dotActive : styles.dotStandby}`} aria-hidden="true" />
          {streaming ? "Scanning" : "Standby"}
        </span>
      </div>
      <div className={styles.traceViewport}>
        <motion.div
          className={styles.beam}
          animate={{ y: ["0%", "100%", "0%"] }}
          transition={{ duration: 2.4, ease: "linear", repeat: Infinity }}
        />
        <pre className={styles.pre}>{displayText}</pre>
      </div>
    </Card>
  );
}
