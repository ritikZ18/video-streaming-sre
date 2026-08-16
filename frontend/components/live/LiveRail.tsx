"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Radio, Clock } from "lucide-react";
import { listLiveEvents } from "../../lib/live";
import { gradientFor } from "../../lib/api";
import type { LiveEvent } from "../../lib/types";

/** Relative "in 5m" / "now" label for an upcoming channel. */
function startsIn(iso?: string | null): string {
  if (!iso) return "soon";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "starting";
  const m = Math.round(diff / 60000);
  if (m < 60) return `in ${m}m`;
  const h = Math.round(m / 60);
  if (h < 24) return `in ${h}h`;
  return `in ${Math.round(h / 24)}d`;
}

/** "Live now" + "Upcoming" rail. Public — appears on the viewer build too. Renders
 *  nothing when there are no live/scheduled channels, so it's invisible until used. */
export function LiveRail({ className = "px-8 pt-6" }: { className?: string }) {
  const [events, setEvents] = useState<LiveEvent[]>([]);

  useEffect(() => {
    let active = true;
    const load = () =>
      listLiveEvents()
        .then((e) => active && setEvents(e))
        .catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, []);

  const live = events.filter((e) => e.state === "live" || e.state === "starting");
  const upcoming = events.filter((e) => e.state === "scheduled");
  if (live.length === 0 && upcoming.length === 0) return null;

  return (
    <section className={className}>
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-red-600/20 text-red-400">
          <Radio className="h-3.5 w-3.5" />
        </span>
        <h2 className="text-lg font-bold tracking-heading">Live &amp; upcoming</h2>
      </div>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {live.map((e) => (
          <LiveCard key={e.id} ev={e} />
        ))}
        {upcoming.map((e) => (
          <LiveCard key={e.id} ev={e} upcoming />
        ))}
      </div>
    </section>
  );
}

function LiveCard({ ev, upcoming }: { ev: LiveEvent; upcoming?: boolean }) {
  const art = ev.backdropUrl || ev.posterUrl;
  const inner = (
    <div className="group relative aspect-video w-64 shrink-0 overflow-hidden rounded-xl ring-1 ring-white/10">
      <div
        className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
        style={art ? { backgroundImage: `url("${art}")` } : { background: gradientFor(ev.id) }}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />

      {upcoming ? (
        <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-amber-500/90 px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-black">
          <Clock className="h-3 w-3" /> {startsIn(ev.scheduledStart)}
        </span>
      ) : (
        <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-white">
          <span className="h-1.5 w-1.5 rounded-full bg-white motion-safe:animate-pulse" /> Live
        </span>
      )}
      {ev.audioOnly && (
        <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white/80">
          Audio
        </span>
      )}

      <div className="absolute inset-x-0 bottom-0 p-3">
        <h3 className="truncate text-sm font-bold text-white">{ev.title}</h3>
        <p className="text-[11px] text-white/60">
          {upcoming ? "Scheduled" : "Streaming now"}
        </p>
      </div>
    </div>
  );

  // Upcoming channels aren't playable yet — no link.
  return upcoming ? inner : <Link href={`/player?live=${ev.id}`}>{inner}</Link>;
}
