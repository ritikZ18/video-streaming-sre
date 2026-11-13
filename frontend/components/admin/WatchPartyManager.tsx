"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CalendarClock, Check, Copy, Loader2, Users } from "lucide-react";
import { listMovies } from "../../lib/api";
import { createPartyRoom } from "../../lib/party";
import type { Movie } from "../../lib/types";

export function WatchPartyManager() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [movieId, setMovieId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listMovies().then((items) => {
      const ready = items.filter((item) => item.manifestUrl && item.status !== "processing");
      setMovies(ready);
      setMovieId((current) => current || ready[0]?.id || "");
    });
  }, []);

  const selected = useMemo(() => movies.find((movie) => movie.id === movieId), [movies, movieId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const result = await createPartyRoom({
        movie_id: selected.id,
        title: selected.title,
        starts_at: startsAt ? new Date(startsAt).toISOString() : undefined,
      });
      setCode(result.code);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create the watch party.");
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    if (!code) return;
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="mt-10 rounded-2xl border border-indigo-400/20 bg-indigo-500/[0.06] p-5">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/20"><Users className="h-5 w-5 text-indigo-200" /></span>
        <div><h2 className="font-bold">Create a watch party</h2><p className="text-xs text-white/50">Guests join the hosted viewer with a system-generated 10-digit code.</p></div>
      </div>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_240px_auto]">
        <select value={movieId} onChange={(event) => setMovieId(event.target.value)} className="rounded-xl border border-white/15 bg-[#171722] px-3 py-2.5 text-sm text-white" required>
          {!movies.length && <option value="">No ready titles</option>}
          {movies.map((movie) => <option value={movie.id} key={movie.id}>{movie.title}</option>)}
        </select>
        <label className="relative"><CalendarClock className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-white/40" /><input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} className="w-full rounded-xl border border-white/15 bg-[#171722] py-2.5 pl-9 pr-3 text-sm text-white" aria-label="Optional scheduled start" /></label>
        <button disabled={busy || !movieId} className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-500 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">{busy && <Loader2 className="h-4 w-4 animate-spin" />}{startsAt ? "Schedule" : "Create now"}</button>
      </form>
      {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}
      {code && <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-4"><div><p className="text-[10px] font-bold uppercase tracking-wider text-emerald-200/60">Guest code</p><p className="font-mono text-2xl tracking-[0.22em] text-emerald-100">{code}</p></div><button type="button" onClick={copyCode} className="ml-auto inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-xs font-semibold">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied ? "Copied" : "Copy code"}</button></div>}
    </section>
  );
}
