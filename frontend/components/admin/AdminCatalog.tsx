"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Loader2,
  Pencil,
  Trash2,
  RefreshCw,
  ImagePlus,
  X,
  Film,
  CheckCircle2,
  Clock,
  Eye,
} from "lucide-react";
import type { Movie } from "../../lib/types";
import {
  listMovies,
  updateMovie,
  uploadArtwork,
  retranscodeMovie,
  deleteMovie,
  type MoviePatch,
} from "../../lib/api";

const VIS: { key: "published" | "unlisted" | "draft"; label: string }[] = [
  { key: "published", label: "Published" },
  { key: "unlisted", label: "Unlisted" },
  { key: "draft", label: "Draft" },
];

function posterOf(m: Movie): string | null {
  return m.posterUrl || m.thumbnailUrl || null;
}

function isProcessing(m: Movie): boolean {
  return m.status === "processing" && !m.manifestUrl;
}

function VisChip({ v }: { v?: Movie["visibility"] }) {
  const map: Record<string, string> = {
    published: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    unlisted: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    draft: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  };
  const k = v ?? "published";
  return <span className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${map[k]}`}>{k}</span>;
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className={`flex h-9 w-9 flex-none items-center justify-center rounded-lg ${tone}`}>{icon}</span>
      <div className="min-w-0">
        <div className="text-xl font-bold leading-none tabular-nums text-white">{value}</div>
        <div className="mt-1 truncate text-[11px] font-medium uppercase tracking-wider text-white/40">{label}</div>
      </div>
    </div>
  );
}

export function AdminCatalog() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<Movie | null>(null);

  const load = useCallback(() => {
    listMovies()
      .then(setMovies)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  // Keep the open drawer in sync with fresh polls (e.g. status flips to ready).
  useEffect(() => {
    if (!editing) return;
    const fresh = movies.find((m) => m.id === editing.id);
    if (fresh && fresh !== editing) setEditing(fresh);
  }, [movies, editing]);

  const stats = useMemo(() => {
    const ready = movies.filter((m) => !isProcessing(m)).length;
    return {
      total: movies.length,
      ready,
      processing: movies.length - ready,
      published: movies.filter((m) => (m.visibility ?? "published") === "published").length,
    };
  }, [movies]);

  return (
    <section className="mt-12">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-heading">Catalog</h2>
          <p className="mt-1 text-xs text-white/50">
            Edit metadata, artwork, visibility, or re-transcode any title.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/70 hover:bg-white/10"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>

      {/* Overview */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={<Film className="h-4 w-4 text-indigo-300" />} tone="bg-indigo-500/15" label="Titles" value={stats.total} />
        <StatCard icon={<CheckCircle2 className="h-4 w-4 text-emerald-300" />} tone="bg-emerald-500/15" label="Ready" value={stats.ready} />
        <StatCard icon={<Clock className="h-4 w-4 text-amber-300" />} tone="bg-amber-500/15" label="Processing" value={stats.processing} />
        <StatCard icon={<Eye className="h-4 w-4 text-sky-300" />} tone="bg-sky-500/15" label="Published" value={stats.published} />
      </div>

      {!loaded ? (
        <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-white/50" /></div>
      ) : movies.length === 0 ? (
        <p className="rounded-xl border border-white/10 bg-white/5 p-8 text-center text-sm text-white/50">
          No titles yet. Upload a video above to get started.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full min-w-[620px] border-collapse text-sm">
            <thead>
              <tr className="bg-white/[0.03] text-left text-[10.5px] uppercase tracking-wider text-white/40">
                <th className="px-4 py-2.5 font-semibold">Title</th>
                <th className="px-4 py-2.5 font-semibold">Status</th>
                <th className="px-4 py-2.5 font-semibold">Visibility</th>
                <th className="px-4 py-2.5 font-semibold">Quality</th>
                <th className="px-4 py-2.5 font-semibold"></th>
              </tr>
            </thead>
            <tbody>
              {movies.map((m) => {
                const v = m.mediaInfo?.video;
                const q = v?.height ? `${v.height}p · ${(v.codec ?? "").toUpperCase()}` : "—";
                const processing = isProcessing(m);
                const pct = Math.max(0, Math.min(100, m.progress ?? 0));
                return (
                  <tr key={m.id} className="border-t border-white/[0.06] hover:bg-white/[0.02]">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <span
                          className="h-11 w-8 flex-none overflow-hidden rounded bg-cover bg-center ring-1 ring-white/10"
                          style={{ backgroundImage: posterOf(m) ? `url(${posterOf(m)})` : m.gradient }}
                        />
                        <span className="line-clamp-2 max-w-[240px] font-medium text-white">{m.title}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      {processing ? (
                        <div className="w-32">
                          <div className="mb-1 flex items-center justify-between text-[10px] text-white/50">
                            <span className="capitalize">{m.stage ?? "queued"}</span>
                            <span className="tabular-nums">{pct}%</span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                            <div className="h-full rounded-full bg-amber-400 transition-[width] duration-500" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-300">
                          <CheckCircle2 className="h-3 w-3" /> ready
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5"><VisChip v={m.visibility} /></td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-white/60">{q}</td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => setEditing(m)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1 text-[11px] font-semibold text-white/80 hover:bg-white/10"
                      >
                        <Pencil className="h-3 w-3" /> Edit
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <EditDrawer
          movie={editing}
          onClose={() => setEditing(null)}
          onChanged={(updated) => {
            setMovies((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
            setEditing(updated);
          }}
          onRemoved={(id) => {
            setMovies((prev) => prev.filter((x) => x.id !== id));
            setEditing(null);
          }}
        />
      )}
    </section>
  );
}

function EditDrawer({
  movie,
  onClose,
  onChanged,
  onRemoved,
}: {
  movie: Movie;
  onClose: () => void;
  onChanged: (m: Movie) => void;
  onRemoved: (id: string) => void;
}) {
  const [form, setForm] = useState<MoviePatch>({
    title: movie.title,
    description: movie.description,
    genre: movie.genre,
    year: movie.year,
    rating: movie.rating,
  });
  const [visibility, setVisibility] = useState(movie.visibility ?? "published");
  // Poster source: "auto" = the frame the worker extracts; "custom" = an uploaded
  // image. Switching to auto + Save clears the custom poster (poster_url = "").
  const [posterMode, setPosterMode] = useState<"auto" | "custom">(movie.posterUrl ? "custom" : "auto");
  const [busy, setBusy] = useState<null | "save" | "retranscode" | "poster" | "backdrop" | "delete">(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const posterInput = useRef<HTMLInputElement>(null);
  const backdropInput = useRef<HTMLInputElement>(null);

  const set = (k: keyof MoviePatch, val: string | number) => setForm((f) => ({ ...f, [k]: val }));
  const flash = (m: string) => {
    setMsg(m);
    setErr(null);
    setTimeout(() => setMsg(null), 2500);
  };

  const save = async () => {
    setBusy("save");
    setErr(null);
    try {
      const patch: MoviePatch = { ...form, visibility };
      // Reset to the auto-extracted frame when the dropdown is on "auto".
      if (posterMode === "auto") patch.poster_url = "";
      const updated = await updateMovie(movie.id, patch);
      onChanged(updated);
      flash("Saved");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const pickArtwork = async (file: File | undefined, kind: "poster" | "backdrop") => {
    if (!file) return;
    setBusy(kind);
    setErr(null);
    try {
      const updated = await uploadArtwork(movie.id, file, kind);
      if (kind === "poster") setPosterMode("custom");
      onChanged(updated);
      flash(kind === "poster" ? "Poster updated" : "Backdrop updated");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const reencode = async () => {
    if (!window.confirm(`Re-transcode "${movie.title}"? It re-runs from the original source; custom artwork is kept.`)) return;
    setBusy("retranscode");
    setErr(null);
    try {
      await retranscodeMovie(movie.id);
      onChanged({ ...movie, status: "processing", progress: 0, stage: "queued", manifestUrl: null });
      flash("Re-transcode started");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete "${movie.title}"? This permanently removes it and its files.`)) return;
    setBusy("delete");
    setErr(null);
    try {
      await deleteMovie(movie.id);
      onRemoved(movie.id);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };

  const poster = posterOf(movie);
  const inp = "w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus:border-white/40";

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-white/10 bg-[#12121b] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-bold tracking-tight">Edit title</h3>
            <p className="mt-0.5 font-mono text-[11px] text-white/40">{movie.id.slice(0, 8)}…</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Artwork */}
        <div className="mb-5 flex gap-4">
          <span
            className="h-36 w-24 flex-none overflow-hidden rounded-lg bg-cover bg-center ring-1 ring-white/10"
            style={{ backgroundImage: poster ? `url(${poster})` : movie.gradient }}
          />
          <div className="flex flex-1 flex-col justify-center gap-2">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Poster</span>
            <select
              value={posterMode}
              onChange={(e) => setPosterMode(e.target.value as "auto" | "custom")}
              className={`${inp} cursor-pointer`}
            >
              <option value="auto">Auto — from video frame</option>
              <option value="custom">Custom — uploaded image</option>
            </select>
            <input ref={posterInput} type="file" accept="image/*" hidden onChange={(e) => pickArtwork(e.target.files?.[0], "poster")} />
            <input ref={backdropInput} type="file" accept="image/*" hidden onChange={(e) => pickArtwork(e.target.files?.[0], "backdrop")} />
            {posterMode === "custom" && (
              <button type="button" disabled={!!busy} onClick={() => posterInput.current?.click()} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-50">
                {busy === "poster" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />} Upload image
              </button>
            )}
            <button type="button" disabled={!!busy} onClick={() => backdropInput.current?.click()} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-50">
              {busy === "backdrop" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />} Replace backdrop
            </button>
          </div>
        </div>

        {/* Metadata */}
        <div className="space-y-3">
          <label className="block"><span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Title</span>
            <input className={inp} value={form.title ?? ""} onChange={(e) => set("title", e.target.value)} /></label>
          <label className="block"><span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Description</span>
            <textarea className={`${inp} min-h-[72px] resize-y`} value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} /></label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block"><span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Genre</span>
              <input className={inp} value={form.genre ?? ""} onChange={(e) => set("genre", e.target.value)} /></label>
            <label className="block"><span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Year</span>
              <input className={inp} type="number" value={form.year ?? ""} onChange={(e) => set("year", Number(e.target.value))} /></label>
            <label className="block"><span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Rating</span>
              <input className={inp} value={form.rating ?? ""} onChange={(e) => set("rating", e.target.value)} /></label>
          </div>
          <div>
            <span className="mb-1.5 block text-[10.5px] font-semibold uppercase tracking-wider text-white/40">Visibility</span>
            <div className="flex gap-2">
              {VIS.map((o) => (
                <button
                  key={o.key}
                  type="button"
                  onClick={() => setVisibility(o.key)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
                    visibility === o.key
                      ? "border-indigo-400/50 bg-indigo-500/20 text-indigo-200"
                      : "border-white/15 bg-white/5 text-white/60 hover:bg-white/10"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {(msg || err) && (
          <p className={`mt-4 text-xs ${err ? "text-rose-400" : "text-emerald-400"}`}>{err ?? msg}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex flex-wrap gap-2 border-t border-white/10 pt-5">
          <button type="button" disabled={!!busy} onClick={save} className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-bold text-black hover:opacity-90 disabled:opacity-50">
            {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" />} Save changes
          </button>
          <button type="button" disabled={!!busy} onClick={reencode} className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm font-semibold text-white/80 hover:bg-white/10 disabled:opacity-50">
            {busy === "retranscode" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Re-transcode
          </button>
          <button type="button" disabled={!!busy} onClick={remove} className="ml-auto inline-flex items-center gap-2 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-300 hover:bg-rose-500/20 disabled:opacity-50">
            {busy === "delete" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Delete
          </button>
        </div>
      </div>
    </div>
  );
}
