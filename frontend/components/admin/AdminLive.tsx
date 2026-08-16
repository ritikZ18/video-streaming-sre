"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Radio,
  Play,
  Square,
  Trash2,
  Copy,
  Check,
  ExternalLink,
  Loader2,
  RefreshCw,
} from "lucide-react";
import {
  adminListLiveEvents,
  createLiveEvent,
  startLiveEvent,
  stopLiveEvent,
  deleteLiveEvent,
  type LiveEventAdmin,
  type CreateLiveEventPayload,
} from "../../lib/live";
import { listMovies } from "../../lib/api";
import type { LiveState, Movie } from "../../lib/types";

const STATE_STYLE: Record<LiveState, string> = {
  idle: "bg-white/10 text-white/60",
  scheduled: "bg-amber-500/20 text-amber-300",
  starting: "bg-sky-500/20 text-sky-300",
  live: "bg-red-500/20 text-red-300",
  ended: "bg-white/10 text-white/40",
  error: "bg-rose-600/20 text-rose-300",
};

const QUALITY_OPTIONS = [
  { value: 480, label: "480p (light)" },
  { value: 720, label: "720p (default)" },
  { value: 1080, label: "1080p (heavy)" },
];

/** Human-friendly "starts in 5m" / "2m ago" for a scheduled timestamp. */
function relTime(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  const m = Math.round(Math.abs(diffMs) / 60000);
  const ahead = diffMs >= 0;
  if (m < 1) return ahead ? "starting now" : "overdue";
  if (m < 60) return ahead ? `starts in ${m}m` : `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return ahead ? `starts in ${h}h` : `${h}h ago`;
  const d = Math.round(h / 24);
  return ahead ? `starts in ${d}d` : `${d}d ago`;
}

export function AdminLive() {
  const [events, setEvents] = useState<LiveEventAdmin[]>([]);
  const [movies, setMovies] = useState<Movie[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const list = await adminListLiveEvents();
      setEvents(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load live channels.");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    void listMovies().then(setMovies).catch(() => {});
    // Poll so a channel that goes live / ends elsewhere stays in sync.
    const id = setInterval(() => void refresh(), 4000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="space-y-6">
      <CreateForm movies={movies} onCreated={refresh} onError={setError} />

      {error && <p className="text-sm text-rose-400">{error}</p>}

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-white/50">
          Channels
        </h2>
        <button
          type="button"
          onClick={() => void refresh()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1 text-xs font-semibold text-white/70 hover:bg-white/10"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>

      {!loaded ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-white/40" />
        </div>
      ) : events.length === 0 ? (
        <p className="rounded-xl bg-white/5 p-6 text-center text-sm text-white/50">
          No live channels yet. Create one above — go live from an uploaded title,
          or open an ingest channel and push from OBS.
        </p>
      ) : (
        <div className="space-y-3">
          {events.map((ev) => (
            <EventCard key={ev.id} ev={ev} onChanged={refresh} onError={setError} />
          ))}
        </div>
      )}
    </div>
  );
}

function CreateForm({
  movies,
  onCreated,
  onError,
}: {
  movies: Movie[];
  onCreated: () => void;
  onError: (m: string) => void;
}) {
  const [sourceType, setSourceType] = useState<"playout" | "ingest">("playout");
  const [title, setTitle] = useState("");
  const [movieId, setMovieId] = useState("");
  const [loop, setLoop] = useState(true);
  const [audioOnly, setAudioOnly] = useState(false);
  const [maxHeight, setMaxHeight] = useState(720);
  const [protocol, setProtocol] = useState<"rtmp" | "srt" | "whip">("rtmp");
  const [scheduledStart, setScheduledStart] = useState("");
  const [recordToVod, setRecordToVod] = useState(false);
  const [busy, setBusy] = useState(false);

  const playable = useMemo(
    () => movies.filter((m) => m.status === "ready" && m.manifestUrl),
    [movies],
  );

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      const payload: CreateLiveEventPayload = {
        title: title || (sourceType === "ingest" ? "Live event" : "Live playout"),
        source_type: sourceType,
        audio_only: audioOnly,
        max_height: maxHeight,
        record_to_vod: recordToVod,
      };
      if (sourceType === "playout") {
        if (!movieId) {
          onError("Pick a title to go live from.");
          setBusy(false);
          return;
        }
        payload.playout_source_movie_id = movieId;
        payload.loop = loop;
      } else {
        payload.ingest_protocol = protocol;
      }
      // A schedule turns the channel "scheduled"; the backend scheduler
      // auto-starts it at this time (a datetime-local is in the viewer's zone).
      if (scheduledStart) {
        payload.scheduled_start = new Date(scheduledStart).toISOString();
      }
      await createLiveEvent(payload);
      setTitle("");
      setScheduledStart("");
      setRecordToVod(false);
      onCreated();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to create channel.");
    } finally {
      setBusy(false);
    }
  };

  const input =
    "w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus:border-white/40";
  const seg = (active: boolean) =>
    `flex-1 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors ${
      active ? "bg-white text-black" : "text-white/60 hover:text-white"
    }`;

  return (
    <form onSubmit={submit} className="rounded-2xl bg-white/5 p-5">
      <div className="mb-4 flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-500/20 text-red-300">
          <Radio className="h-4 w-4" />
        </span>
        <div>
          <h2 className="text-base font-bold tracking-tight">New live channel</h2>
          <p className="text-xs text-white/50">
            Re-stream an uploaded title, or open an ingest slot for a real encoder.
          </p>
        </div>
      </div>

      <div className="mb-4 flex gap-1 rounded-lg bg-white/5 p-1">
        <button type="button" className={seg(sourceType === "playout")} onClick={() => setSourceType("playout")}>
          From an upload
        </button>
        <button type="button" className={seg(sourceType === "ingest")} onClick={() => setSourceType("ingest")}>
          Encoder ingest
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-white/50">Channel title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={sourceType === "ingest" ? "Live event" : "Live playout"}
            className={input}
          />
        </label>

        {sourceType === "playout" ? (
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-white/50">Source title</span>
            <select value={movieId} onChange={(e) => setMovieId(e.target.value)} className={input}>
              <option value="">Select a title…</option>
              {playable.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-white/50">Push protocol</span>
            <select
              value={protocol}
              onChange={(e) => setProtocol(e.target.value as "rtmp" | "srt" | "whip")}
              className={input}
            >
              <option value="rtmp">RTMP (OBS)</option>
              <option value="srt">SRT</option>
              <option value="whip">WHIP (browser)</option>
            </select>
          </label>
        )}

        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-white/50">Quality ceiling</span>
          <select
            value={maxHeight}
            onChange={(e) => setMaxHeight(Number(e.target.value))}
            className={input}
            disabled={audioOnly}
          >
            {QUALITY_OPTIONS.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-end gap-4 pb-1">
          <label className="flex items-center gap-2 text-sm text-white/70">
            <input
              type="checkbox"
              checked={audioOnly}
              onChange={(e) => setAudioOnly(e.target.checked)}
              className="h-4 w-4 accent-red-500"
            />
            Audio only
          </label>
          {sourceType === "playout" && (
            <label className="flex items-center gap-2 text-sm text-white/70">
              <input
                type="checkbox"
                checked={loop}
                onChange={(e) => setLoop(e.target.checked)}
                className="h-4 w-4 accent-red-500"
              />
              Loop
            </label>
          )}
          <label
            className="flex items-center gap-2 text-sm text-white/70"
            title="Keep the finished stream as a replay VOD (no re-encode)"
          >
            <input
              type="checkbox"
              checked={recordToVod}
              onChange={(e) => setRecordToVod(e.target.checked)}
              className="h-4 w-4 accent-red-500"
            />
            Save replay
          </label>
        </div>
      </div>

      <label className="mt-3 block max-w-xs">
        <span className="mb-1 block text-xs font-semibold text-white/50">
          Schedule start <span className="text-white/30">(optional)</span>
        </span>
        <input
          type="datetime-local"
          value={scheduledStart}
          onChange={(e) => setScheduledStart(e.target.value)}
          className={input}
        />
        <span className="mt-1 block text-[11px] text-white/30">
          Leave empty to start it manually. When set, the channel auto-starts at this time.
        </span>
      </label>

      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-bold text-black transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radio className="h-4 w-4" />}
          Create channel
        </button>
      </div>
    </form>
  );
}

function EventCard({
  ev,
  onChanged,
  onError,
}: {
  ev: LiveEventAdmin;
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    onError("");
    try {
      await fn();
      onChanged();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  };

  const isLive = ev.state === "live" || ev.state === "starting";

  return (
    <div className="rounded-xl bg-white/5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide ${STATE_STYLE[ev.state]}`}>
          {ev.state}
        </span>
        <span className="font-semibold text-white">{ev.title}</span>
        <span className="text-xs text-white/40">
          {ev.sourceType === "ingest" ? `ingest · ${ev.ingestProtocol ?? "rtmp"}` : "playout"}
          {ev.audioOnly ? " · audio" : ` · ≤${ev.maxHeight ?? 720}p`}
        </span>

        <div className="ml-auto flex items-center gap-2">
          {isLive ? (
            <a
              href={`/player?live=${ev.id}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-white/20"
            >
              <ExternalLink className="h-3.5 w-3.5" /> Watch
            </a>
          ) : null}
          {ev.state === "live" || ev.state === "starting" ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => stopLiveEvent(ev.id))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-white/20 disabled:opacity-40"
            >
              <Square className="h-3.5 w-3.5" /> End
            </button>
          ) : (
            <button
              type="button"
              disabled={busy || ev.state === "ended"}
              onClick={() => act(() => startLiveEvent(ev.id))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-bold text-white hover:bg-red-500 disabled:opacity-40"
            >
              <Play className="h-3.5 w-3.5" /> Go live
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => act(() => deleteLiveEvent(ev.id))}
            className="inline-flex items-center justify-center rounded-lg border border-white/10 p-1.5 text-white/50 hover:bg-white/10 hover:text-rose-300 disabled:opacity-40"
            aria-label="Delete channel"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {ev.state === "scheduled" && ev.scheduledStart && (
        <p className="mt-2 text-xs text-amber-300/80">
          Scheduled for {new Date(ev.scheduledStart).toLocaleString()} · {relTime(ev.scheduledStart)}
        </p>
      )}

      {ev.errorDetail && <p className="mt-2 text-xs text-rose-400">{ev.errorDetail}</p>}

      {/* Ingest push details — only for ingest channels, admin-only secret. */}
      {ev.sourceType === "ingest" && ev.ingestUrl && (
        <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
          <p className="text-[11px] text-white/40">
            Point your encoder here — the channel goes <b>live automatically</b> the
            moment it connects (or hit <b>Go live</b> to force it):
          </p>
          <CopyRow label="Push URL" value={ev.ingestUrl} />
          {ev.streamKey && <CopyRow label="Stream key" value={ev.streamKey} secret />}
        </div>
      )}
    </div>
  );
}

function CopyRow({ label, value, secret }: { label: string; value: string; secret?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[11px] font-semibold uppercase tracking-wide text-white/40">
        {label}
      </span>
      <code className="flex-1 truncate rounded bg-black/40 px-2 py-1 font-mono text-xs text-white/70">
        {secret ? value.replace(/./g, "•") : value}
      </code>
      <button
        type="button"
        onClick={copy}
        className="inline-flex items-center justify-center rounded border border-white/10 p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
        aria-label={`Copy ${label}`}
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
