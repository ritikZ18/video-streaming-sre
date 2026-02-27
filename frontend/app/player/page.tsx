"use client";

import { useEffect, useState } from "react";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { VideoPlayer } from "../../components/player/VideoPlayer";
import { StatsOverlay } from "../../components/player/StatsOverlay";

export default function PlayerPage() {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setUrl(params.get("url"));
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-black text-white">
      <Navbar onAddMovieClick={() => {}} />
      <main className="flex-1 pt-16">
        <section className="flex flex-col items-center justify-center px-4 py-8">
          <div className="w-full max-w-5xl">
            <VideoPlayer src={url} />
            <div className="mt-4">
              <StatsOverlay />
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}

