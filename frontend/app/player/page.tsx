"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, Loader2 } from "lucide-react";
import { Navbar } from "../../components/layout/Navbar";
import { VideoPlayer } from "../../components/player/VideoPlayer";
import { getMovie } from "../../lib/api";
import type { SubtitleTrack } from "../../lib/types";

export default function PlayerPage() {
  const [p, setP] = useState<{
    url: string | null;
    title: string | null;
    poster: string | null;
    id: string | null;
  }>({ url: null, title: null, poster: null, id: null });
  const [subs, setSubs] = useState<SubtitleTrack[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search);
    const id = q.get("id");
    const urlParam = q.get("url"); // legacy / seed fallback
    setP({ url: urlParam, title: q.get("title"), poster: q.get("poster"), id });

    // Preferred path: only an id is in the URL — fetch everything server-side so
    // the manifest/poster URLs never appear in the address bar.
    if (id) {
      setLoading(!urlParam);
      void getMovie(id)
        .then((m) => {
          if (m) {
            setSubs(m.subtitleTracks ?? []);
            setP((prev) => ({
              url: m.manifestUrl ?? prev.url,
              title: m.title ?? prev.title,
              poster: m.thumbnailUrl ?? prev.poster,
              id,
            }));
          }
        })
        .finally(() => setLoading(false));
    }
  }, []);

  return (
    <div className="flex h-screen flex-col overflow-hidden text-white">
      <Navbar />
      <main className="flex flex-1 items-center justify-center px-4 pt-16 pb-4">
        <div
          className="relative w-full"
          style={{ maxWidth: "calc((100vh - 9rem) * 16 / 9)" }}
        >
          <button
            type="button"
            onClick={() => window.history.back()}
            className="absolute -top-8 left-0 z-10 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-white/70 hover:text-white"
          >
            <ChevronLeft className="h-4 w-4" /> Back
          </button>
          {loading ? (
            <div className="flex aspect-video w-full items-center justify-center rounded-2xl bg-zinc-900 ring-1 ring-white/10">
              <Loader2 className="h-10 w-10 animate-spin text-white/70" />
            </div>
          ) : (
            <VideoPlayer
              src={p.url}
              title={p.title}
              poster={p.poster}
              contentId={p.id}
              subtitleTracks={subs}
            />
          )}
        </div>
      </main>
    </div>
  );
}
