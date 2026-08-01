"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Zap, AlertTriangle, Users, Radio, Gauge, Loader2, Film, Sparkles } from "lucide-react";
import { fetchQoeStats, listMovies, type QoeStats } from "../../lib/api";
import type { Movie } from "../../lib/types";

// Health → color. Lower-is-better metrics (startup, rebuffer) and higher-is-better
// (rebuffer-free %) each get their own thresholds.
type Tone = "good" | "warn" | "bad" | "idle";
const toneClass: Record<Tone, string> = {
  good: "text-emerald-300 bg-emerald-500/15",
  warn: "text-amber-300 bg-amber-500/15",
  bad: "text-rose-300 bg-rose-500/15",
  idle: "text-white/60 bg-white/10",
};

function startupTone(ms: number): Tone {
  if (!ms) return "idle";
  return ms < 2000 ? "good" : ms < 4000 ? "warn" : "bad";
}
function freeTone(pct: number): Tone {
  return pct >= 99 ? "good" : pct >= 95 ? "warn" : "bad";
}
function ratioTone(r: number): Tone {
  return r < 0.05 ? "good" : r < 0.15 ? "warn" : "bad";
}

/** Seconds → a compact human duration ("2m 40s", "1h 3m", "45s"). */
function fmtDur(sec: number | null): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  const t = Math.max(0, Math.round(sec));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}

function StatCard({
  icon,
  label,
  value,
  sub,
  tone = "idle",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-center gap-2">
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${toneClass[tone]}`}>{icon}</span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-white/40">{label}</span>
      </div>
      <div className="mt-3 text-2xl font-bold tabular-nums text-white">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-white/45">{sub}</div>}
    </div>
  );
}

// I/O Framer interpolation status → pill styling.
const interpPill: Record<string, string> = {
  queued: "text-white/60 border-white/15 bg-white/5",
  processing: "text-sky-300 border-sky-400/30 bg-sky-400/10",
  done: "text-emerald-300 border-emerald-400/30 bg-emerald-400/10",
  skipped: "text-amber-300 border-amber-400/30 bg-amber-400/10",
  failed: "text-rose-300 border-rose-400/30 bg-rose-400/10",
};

const eventColor: Record<string, string> = {
  startup: "text-sky-300 border-sky-400/30 bg-sky-400/10",
  rebuffer: "text-amber-300 border-amber-400/30 bg-amber-400/10",
  bitrate_switch: "text-indigo-300 border-indigo-400/30 bg-indigo-400/10",
  heartbeat: "text-white/50 border-white/15 bg-white/5",
  error: "text-rose-300 border-rose-400/30 bg-rose-400/10",
};

export function AdminObservability() {
  const [stats, setStats] = useState<QoeStats | null>(null);
  const [movies, setMovies] = useState<Movie[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState(false);
  // Ticks every second so interpolation elapsed / ETA count up smoothly between
  // the 4s catalog polls.
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const load = useCallback(() => {
    fetchQoeStats()
      .then((s) => {
        setStats(s);
        setErr(false);
      })
      .catch(() => setErr(true))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);

  // Poll the catalog for the content_id → title map AND live encode status.
  useEffect(() => {
    const loadMovies = () => {
      listMovies().then(setMovies).catch(() => {});
    };
    loadMovies();
    const t = setInterval(loadMovies, 4000);
    return () => clearInterval(t);
  }, []);

  const titles = useMemo(
    () => new Map(movies.map((m) => [m.id, m.title] as const)),
    [movies],
  );
  // Titles the worker is actively encoding — including re-encodes / audio
  // re-segmenting of titles that already have a (still-playable) manifest.
  const encoding = useMemo(
    () => movies.filter((m) => m.status === "processing"),
    [movies],
  );
  // Titles with any frame-interpolation activity (I/O Framer): request + state.
  const interpJobs = useMemo(
    () => movies.filter((m) => m.interpStatus),
    [movies],
  );

  const titleOf = useCallback(
    (id: string | null) => (id && titles.get(id)) || (id ? `${id.slice(0, 8)}…` : "—"),
    [titles],
  );

  const now = stats?.generated_at ?? 0;
  const rel = useMemo(
    () => (ts: number) => {
      const d = Math.max(0, Math.round(now - ts));
      return d < 60 ? `${d}s ago` : `${Math.floor(d / 60)}m ago`;
    },
    [now],
  );

  if (!loaded) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-white/50" />
      </div>
    );
  }

  if (err || !stats) {
    return (
      <p className="rounded-xl border border-white/10 bg-white/5 p-8 text-center text-sm text-white/50">
        Beacon collector unreachable. Is the stack running?
      </p>
    );
  }

  const s = stats;
  const mins = Math.round(s.window_seconds / 60);
  const empty = s.sessions.total === 0;

  return (
    <section className="mt-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-heading">Playback health · QoE</h2>
          <p className="mt-1 text-xs text-white/50">
            Live client-measured Quality of Experience · rolling {mins}-minute window
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
          <Radio className="h-3 w-3 animate-pulse" /> live
        </span>
      </div>

      {/* Headline cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={<Users className="h-4 w-4" />}
          label="Active sessions"
          value={String(s.sessions.active)}
          sub={`${s.sessions.total} in window`}
          tone={s.sessions.active > 0 ? "good" : "idle"}
        />
        <StatCard
          icon={<Activity className="h-4 w-4" />}
          label="Rebuffer-free"
          value={`${s.sessions.rebuffer_free_pct}%`}
          sub={`${s.rebuffer.sessions_affected} affected · ${s.rebuffer.events} events`}
          tone={empty ? "idle" : freeTone(s.sessions.rebuffer_free_pct)}
        />
        <StatCard
          icon={<Zap className="h-4 w-4" />}
          label="Startup p95"
          value={s.startup_ms.p95 ? `${(s.startup_ms.p95 / 1000).toFixed(2)}s` : "—"}
          sub={`p50 ${s.startup_ms.p50} ms · avg ${s.startup_ms.avg} ms`}
          tone={startupTone(s.startup_ms.p95)}
        />
        <StatCard
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Errors"
          value={String(s.errors.total)}
          sub={`avg bitrate ${s.bitrate_kbps.avg ? `${(s.bitrate_kbps.avg / 1000).toFixed(1)} Mbps` : "—"}`}
          tone={s.errors.total === 0 ? "good" : "bad"}
        />
      </div>

      {/* Transcode jobs — live encode progress from the catalog (upload-api) */}
      <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
        <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.03] px-4 py-2.5">
          <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
            <Film className="h-3.5 w-3.5" /> Transcode jobs
          </span>
          <span className="tabular-nums text-[11px] text-white/40">{encoding.length} active</span>
        </div>
        {encoding.length === 0 ? (
          <p className="px-4 py-5 text-center text-sm text-white/40">
            No active encodes — everything&apos;s ready.
          </p>
        ) : (
          <ul className="divide-y divide-white/[0.06]">
            {encoding.map((m) => {
              const pct = Math.max(0, Math.min(100, m.progress ?? 0));
              return (
                <li key={m.id} className="px-4 py-3">
                  <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
                    <span className="truncate text-white">{m.title}</span>
                    <span className="flex items-center gap-2 whitespace-nowrap text-[11px] text-white/50">
                      <span className="capitalize">{m.stage ?? "queued"}</span>
                      <span className="tabular-nums">{pct}%</span>
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-fuchsia-400 transition-[width] duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Frame interpolation — I/O Framer status + reason per title */}
      {interpJobs.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
          <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.03] px-4 py-2.5">
            <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
              <Sparkles className="h-3.5 w-3.5" /> Frame interpolation · I/O Framer
            </span>
            <span className="tabular-nums text-[11px] text-white/40">
              {interpJobs.filter((m) => m.interpStatus === "processing").length} active
            </span>
          </div>
          <ul className="divide-y divide-white/[0.06]">
            {interpJobs.map((m) => {
              const active = m.interpStatus === "processing";
              // During the interpolation pass, prefer the I/O Framer's own 0-100 +
              // stage (granular, and where the time actually goes on CPU); during
              // the ladder encode fall back to the worker's overall progress.
              const interpolating = active && m.stage === "interpolating";
              const pct = Math.max(
                0,
                Math.min(100, (interpolating ? m.interpProgress : m.progress) ?? 0),
              );
              const stageLabel = interpolating
                ? m.interpStage ?? "interpolating"
                : m.stage ?? "working";
              const elapsed =
                active && m.interpStartedAt ? Math.max(0, nowMs / 1000 - m.interpStartedAt) : null;
              // ETA only while interpolating (elapsed maps cleanly onto its 0-100);
              // once encoding it's near the end, so we just show the stage/%.
              const eta =
                interpolating && pct > 3 && elapsed != null ? (elapsed * (100 - pct)) / pct : null;
              return (
                <li key={m.id} className="px-4 py-2.5 text-sm">
                  <div className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 truncate text-white">{m.title}</span>
                    {m.interpTargetFps ? (
                      <span className="whitespace-nowrap text-[11px] tabular-nums text-white/45">
                        → {m.interpTargetFps} fps
                      </span>
                    ) : null}
                    {active ? (
                      <span className="flex items-center gap-2 whitespace-nowrap text-[11px] text-white/55">
                        <span className="capitalize">{stageLabel}</span>
                        <span className="tabular-nums text-white/75">{pct}%</span>
                        {elapsed != null && <span className="text-white/35">· {fmtDur(elapsed)}</span>}
                        {eta != null && <span className="text-sky-300/80">· ~{fmtDur(eta)} left</span>}
                      </span>
                    ) : m.interpDetail ? (
                      <span
                        className="hidden max-w-[260px] truncate text-[11px] text-white/40 sm:inline"
                        title={m.interpDetail}
                      >
                        {m.interpDetail}
                      </span>
                    ) : null}
                    <span
                      className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-semibold capitalize ${
                        interpPill[m.interpStatus ?? "queued"] ?? interpPill.queued
                      }`}
                    >
                      {active && <Loader2 className="h-3 w-3 animate-spin" />}
                      {m.interpStatus}
                    </span>
                  </div>
                  {active && (
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-sky-400 to-indigo-400 transition-[width] duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {empty && (
        <p className="mt-4 rounded-xl border border-white/10 bg-white/5 p-6 text-center text-sm text-white/50">
          No playback in the last {mins} minutes. Play a title (even in another tab) and the metrics stream in live.
        </p>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        {/* Per-title breakdown */}
        <div className="overflow-hidden rounded-xl border border-white/10">
          <div className="border-b border-white/10 bg-white/[0.03] px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-white/40">
            Per-title QoE
          </div>
          {s.top_content.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-white/40">No sessions yet.</p>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-[10.5px] uppercase tracking-wider text-white/35">
                  <th className="px-4 py-2 font-semibold">Title</th>
                  <th className="px-4 py-2 text-right font-semibold">Sessions</th>
                  <th className="px-4 py-2 text-right font-semibold">Startup p95</th>
                  <th className="px-4 py-2 text-right font-semibold">Rebuffer</th>
                </tr>
              </thead>
              <tbody>
                {s.top_content.map((c) => (
                  <tr key={c.content_id} className="border-t border-white/[0.06]">
                    <td className="max-w-[220px] truncate px-4 py-2 text-white">{titleOf(c.content_id)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-white/70">{c.sessions}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      <span className={`rounded px-1.5 py-0.5 ${toneClass[startupTone(c.startup_p95_ms)]}`}>
                        {c.startup_p95_ms ? `${c.startup_p95_ms} ms` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      <span className={`rounded px-1.5 py-0.5 ${toneClass[ratioTone(c.rebuffer_ratio)]}`}>
                        {(c.rebuffer_ratio * 100).toFixed(0)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Errors + live feed */}
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-white/10 p-4">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
              <Gauge className="h-3.5 w-3.5" /> Errors by type
            </div>
            {Object.keys(s.errors.by_type).length === 0 ? (
              <p className="text-sm text-emerald-300/80">None 🎉</p>
            ) : (
              <ul className="space-y-1.5">
                {Object.entries(s.errors.by_type).map(([type, n]) => (
                  <li key={type} className="flex items-center justify-between gap-3 text-xs">
                    <span className="truncate font-mono text-rose-300">{type}</span>
                    <span className="tabular-nums text-white/60">{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="min-h-[180px] rounded-xl border border-white/10 p-4">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">Live event feed</div>
            {s.recent_events.length === 0 ? (
              <p className="text-sm text-white/40">Waiting for events…</p>
            ) : (
              <ul className="space-y-1.5">
                {s.recent_events.slice(0, 12).map((e, i) => (
                  <li key={`${e.session_id}-${e.ts}-${i}`} className="flex items-center gap-2 text-[11px]">
                    <span className={`rounded border px-1.5 py-0.5 font-semibold ${eventColor[e.event] ?? eventColor.heartbeat}`}>
                      {e.event}
                    </span>
                    <span className="truncate text-white/60">{titleOf(e.content_id)}</span>
                    {e.detail && <span className="tabular-nums text-white/40">{e.detail}</span>}
                    <span className="ml-auto whitespace-nowrap text-white/30">{rel(e.ts)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
