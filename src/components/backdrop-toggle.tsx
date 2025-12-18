"use client";

import { useEffect, useState } from "react";

export function BackdropToggle() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("cosmosEffects");
    if (stored === "on") {
      setEnabled(true);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("cosmosEffects", enabled ? "on" : "off");
  }, [enabled]);

  return (
    <div className="flex items-center gap-2 text-sm text-slate-200">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={() => setEnabled((v) => !v)}
          className="h-4 w-4 accent-cyan-300"
        />
        Cosmic effects
      </label>
      {!enabled && <span className="text-xs text-slate-400">(muted)</span>}
      <style jsx global>{`
        :root {
          --cosmos-enabled: ${enabled ? "1" : "0"};
        }
      `}</style>
    </div>
  );
}
