"use client";

import { useState } from "react";

export function StatsOverlay() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative mt-2 flex justify-end">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="rounded-lg bg-white/10 px-3 py-1 text-xs font-semibold text-white hover:bg-white/20"
      >
        {open ? "Hide Stats" : "Show Stats"}
      </button>
      {open && (
        <div className="absolute right-0 top-9 w-64 rounded-xl bg-black/70 p-3 text-[11px] text-white/80 backdrop-blur-xl">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
            QoE (placeholder)
          </div>
          <ul className="space-y-1">
            <li>Startup time: —</li>
            <li>Bitrate: —</li>
            <li>Buffer length: —</li>
            <li>Rebuffers: —</li>
          </ul>
        </div>
      )}
    </div>
  );
}

