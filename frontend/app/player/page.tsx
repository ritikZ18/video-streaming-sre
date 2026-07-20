"use client";

import { useEffect, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { VideoPlayer } from "../../components/player/VideoPlayer";

export default function PlayerPage() {
  const [p, setP] = useState<{
    url: string | null;
    title: string | null;
    poster: string | null;
    id: string | null;
  }>({ url: null, title: null, poster: null, id: null });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search);
    setP({
      url: q.get("url"),
      title: q.get("title"),
      poster: q.get("poster"),
      id: q.get("id"),
    });
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-black text-white">
      <Navbar />
      <main className="flex-1 pt-16">
        <section className="mx-auto w-full max-w-5xl px-4 py-8">
          <button
            type="button"
            onClick={() => window.history.back()}
            className="mb-4 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-white/70 hover:text-white"
          >
            <ChevronLeft className="h-4 w-4" /> Back
          </button>

          <VideoPlayer src={p.url} title={p.title} poster={p.poster} contentId={p.id} />

          {p.title && (
            <h1 className="mt-4 text-xl font-bold tracking-tight">{p.title}</h1>
          )}
        </section>
      </main>
      <Footer />
    </div>
  );
}
