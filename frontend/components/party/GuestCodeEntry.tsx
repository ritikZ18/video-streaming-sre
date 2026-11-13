"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, KeyRound, ShieldCheck, Wifi } from "lucide-react";
import { backendBase } from "../../lib/backend";

export function GuestCodeEntry({ compact = false }: { compact?: boolean }) {
  const [code, setCode] = useState("");

  // Adopt and persist ?api=<cloudflare gateway> even when the shared URL lands
  // on /admin instead of the home page. Navigation to /party then stays wired
  // to that same tunnel after backendBase strips the query parameter.
  useEffect(() => { backendBase(); }, []);

  function join(event: FormEvent) {
    event.preventDefault();
    if (code.length !== 10) return;
    window.location.assign(`/party?code=${code}`);
  }

  return (
    <form onSubmit={join} className={compact ? "w-full" : "relative overflow-hidden rounded-3xl border border-violet-400/20 bg-[#181825] p-7 shadow-2xl shadow-violet-950/30 sm:p-9"}>
      {!compact && <div className="pointer-events-none absolute -right-16 -top-20 h-52 w-52 rounded-full bg-violet-500/15 blur-3xl" />}
      <div className={compact ? "" : "relative"}>
        {!compact && <span className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 shadow-lg shadow-violet-900/30"><KeyRound className="h-5 w-5" /></span>}
        <p className="text-[10px] font-extrabold uppercase tracking-[.2em] text-violet-300">Private screening</p>
        <h1 className={`${compact ? "mt-1 text-base" : "mt-2 text-2xl"} font-bold tracking-tight text-white`}>Enter your watch-party code</h1>
        <p className="mt-2 text-sm leading-6 text-white/50">Use the 10-digit code shared by the host to enter the theater.</p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <input value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 10))} inputMode="numeric" autoComplete="one-time-code" autoFocus={!compact} placeholder="0000000000" aria-label="10-digit watch-party code" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#0f0f19] px-4 py-3 text-center font-mono text-xl font-bold tracking-[.22em] text-white outline-none transition-colors placeholder:text-white/15 focus:border-violet-400/60" />
          <button type="submit" disabled={code.length !== 10} className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-500 px-5 py-3 text-sm font-extrabold text-white shadow-lg shadow-violet-950/30 transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-35">Enter theater <ArrowRight className="h-4 w-4" /></button>
        </div>
        {!compact && <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 border-t border-white/[.07] pt-5 text-[10px] font-semibold uppercase tracking-wider text-white/35"><span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-violet-300" />Code protected</span><span className="inline-flex items-center gap-1.5"><Wifi className="h-3.5 w-3.5 text-violet-300" />Live room connection</span></div>}
      </div>
    </form>
  );
}
