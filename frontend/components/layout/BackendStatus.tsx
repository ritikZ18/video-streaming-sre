"use client";

import { useEffect, useState } from "react";
import { Wifi } from "lucide-react";
import { backendOverride, clearBackendOverride } from "../../lib/backend";

/** Small pill shown once the viewer has adopted a runtime backend (via a ?api=
 *  link). Clicking forgets it and reloads — the recovery path for a device that
 *  cached a tunnel address that has since died. Renders nothing when no runtime
 *  backend is set (local dev / same-host deploy). */
export function BackendStatus() {
  const [base, setBase] = useState<string | null>(null);

  // Read after mount only — localStorage is client-only, and this avoids a
  // hydration mismatch between the server (null) and the client value.
  useEffect(() => {
    setBase(backendOverride());
  }, []);

  if (!base) return null;

  let host = base;
  try {
    host = new URL(base).host;
  } catch {
    /* keep the raw string */
  }

  return (
    <button
      type="button"
      onClick={() => {
        clearBackendOverride();
        window.location.reload();
      }}
      title={`Connected to ${base} — click to disconnect (forget this backend)`}
      className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-300 transition-colors hover:bg-emerald-400/20"
    >
      <Wifi className="h-3.5 w-3.5" />
      <span className="max-w-[140px] truncate">{host}</span>
    </button>
  );
}
