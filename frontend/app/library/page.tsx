"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, UploadCloud, X } from "lucide-react";
import type { Movie } from "../../lib/types";
import { listMovies, cancelJob } from "../../lib/api";
import { getAdminToken } from "../../lib/auth";
import { dedupeByTitle } from "../../lib/catalog";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { MovieCard } from "../../components/movie/MovieCard";
import { MovieDetail } from "../../components/movie/MovieDetail";

export default function LibraryPage() {
  const [uploads, setUploads] = useState<Movie[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<Movie | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [canceling, setCanceling] = useState<Record<string, boolean>>({});

  // Admin gate for the Stop button (cancel is admin-only server-side).
  useEffect(() => {
    setIsAdmin(getAdminToken() !== null);
  }, []);

  // Stop a still-processing transcode. m.id === the transcode job id.
  const stopJob = async (id: string) => {
    setCanceling((c) => ({ ...c, [id]: true }));
    try {
      await cancelJob(id);
      // Optimistically drop it; the 5s poll confirms it's gone.
      setUploads((u) => u.filter((m) => m.id !== id));
    } catch {
      setCanceling((c) => ({ ...c, [id]: false }));
    }
  };

  // Only the real catalog (your uploads) — polled so processing → ready flips live.
  useEffect(() => {
    let active = true;
    const load = () => {
      listMovies()
        .then((r) => {
          if (active) {
            setUploads(r);
            setLoaded(true);
          }
        })
        .catch(() => {
          if (active) setLoaded(true);
        });
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, []);

  const playMovie = (movie: Movie) => {
    if (!movie.manifestUrl) return;
    window.location.href = `/player?id=${encodeURIComponent(movie.id)}`;
  };

  const { ready, processing } = useMemo(() => {
    const deduped = dedupeByTitle(uploads);
    return {
      ready: deduped.filter((m) => m.status !== "processing" || m.manifestUrl),
      processing: deduped.filter((m) => m.status === "processing" && !m.manifestUrl),
    };
  }, [uploads]);

  return (
    <div className="min-h-screen text-white">
      <Navbar />
      <main className="px-8 pt-24 pb-16">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-heading">Your Library</h1>
            <p className="mt-1 text-sm text-white/60">
              {uploads.length} uploaded {uploads.length === 1 ? "title" : "titles"}
              {processing.length > 0 && ` · ${processing.length} processing`} · streamed from your own origin.
            </p>
          </div>
          <a
            href="/admin"
            className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-white/20"
          >
            <UploadCloud className="h-4 w-4" /> Upload
          </a>
        </div>

        {loaded && uploads.length === 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/5 p-12 text-center">
            <UploadCloud className="mx-auto mb-3 h-8 w-8 text-white/40" />
            <p className="text-sm text-white/70">No uploads yet.</p>
            <p className="mt-1 text-xs text-white/45">
              Head to{" "}
              <a href="/admin" className="text-white underline">
                Admin
              </a>{" "}
              to upload a video — it will appear here once it starts transcoding.
            </p>
          </div>
        )}

        {processing.length > 0 && (
          <section className="mb-10">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/50">
              Processing
            </h2>
            <div className="space-y-2">
              {processing.map((m) => (
                <div
                  key={m.id}
                  className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
                >
                  <div className="flex items-center gap-3">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-white/70" />
                    <div className="min-w-0 flex-1 truncate text-sm font-semibold">{m.title}</div>
                    <div className="shrink-0 text-[11px] text-white/55">
                      {m.stage && m.stage !== "queued" ? `${m.stage} · ` : ""}
                      {m.progress ?? 0}%
                    </div>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => stopJob(m.id)}
                        disabled={canceling[m.id]}
                        title="Stop transcoding"
                        className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold text-rose-300 transition-colors hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {canceling[m.id] ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <X className="h-3 w-3" />
                        )}
                        {canceling[m.id] ? "Stopping…" : "Stop"}
                      </button>
                    )}
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full bg-white transition-all"
                      style={{ width: `${m.progress ?? 0}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {ready.length > 0 && (
          <section>
            {processing.length > 0 && (
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/50">
                Ready to watch
              </h2>
            )}
            <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] justify-items-center gap-x-4 gap-y-7">
              {ready.map((m) => (
                <MovieCard key={m.id} movie={m} onClick={setSelected} size="normal" />
              ))}
            </div>
          </section>
        )}
      </main>
      <Footer />
      {selected && (
        <MovieDetail movie={selected} onClose={() => setSelected(null)} onPlay={playMovie} />
      )}
    </div>
  );
}
