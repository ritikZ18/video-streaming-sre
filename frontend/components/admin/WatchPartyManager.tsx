"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CalendarDays, Check, ChevronRight, Clock3, Copy, ExternalLink, Film, Loader2, Play, Radio, Sparkles } from "lucide-react";
import { listMovies } from "../../lib/api";
import { createPartyRoom, fetchPartyAdminStats } from "../../lib/party";
import type { Movie } from "../../lib/types";
import styles from "./WatchPartyManager.module.css";

type ScheduleMode = "now" | "later";
type CreatedParty = { code: string; startsAt?: string };
const pad = (value: number) => String(value).padStart(2, "0");
const localParts = (date: Date) => ({ date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`, time: `${pad(date.getHours())}:${pad(date.getMinutes())}` });
const durationSeconds = (runtime: string) => {
  const hours = Number(runtime.match(/(\d+)\s*h/i)?.[1] ?? 0);
  const minutes = Number(runtime.match(/(\d+)\s*m/i)?.[1] ?? 0);
  const seconds = Number(runtime.match(/(\d+)\s*s/i)?.[1] ?? 0);
  return hours * 3600 + minutes * 60 + seconds;
};

function countdown(target: number, now: number) {
  const seconds = Math.max(0, Math.floor((target - now) / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return [days ? `${days}d` : null, hours ? `${hours}h` : null, `${minutes}m`].filter(Boolean).join(" ");
}

export function WatchPartyManager() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [movieId, setMovieId] = useState("");
  const [mode, setMode] = useState<ScheduleMode>("now");
  const initial = useMemo(() => localParts(new Date(Date.now() + 30 * 60_000)), []);
  const [date, setDate] = useState(initial.date);
  const [time, setTime] = useState(initial.time);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<CreatedParty | null>(null);
  const [copied, setCopied] = useState<"code" | "link" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [partyStates, setPartyStates] = useState<Map<string, string>>(new Map());

  useEffect(() => { void listMovies().then((items) => { const ready = items.filter((item) => item.manifestUrl && item.status !== "processing"); setMovies(ready); setMovieId((current) => current || ready[0]?.id || ""); }); }, []);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30_000); return () => window.clearInterval(timer); }, []);
  useEffect(() => {
    const load = () => { void fetchPartyAdminStats().then((result) => setPartyStates(new Map(result.rooms.filter((room) => room.state !== "ended").map((room) => [room.movie_id, room.state])))).catch(() => {}); };
    load(); const timer = window.setInterval(load, 5000); return () => window.clearInterval(timer);
  }, []);

  const selected = useMemo(() => movies.find((movie) => movie.id === movieId), [movies, movieId]);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const scheduledDate = useMemo(() => new Date(`${date}T${time}`), [date, time]);
  const scheduleValid = mode === "now" || (Number.isFinite(scheduledDate.getTime()) && scheduledDate.getTime() > now);
  const exactStart = scheduleValid && mode === "later" ? new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(scheduledDate) : "Starts as soon as the room is created";

  function applyPreset(kind: "30" | "tonight" | "tomorrow") {
    const target = new Date();
    if (kind === "30") target.setTime(target.getTime() + 30 * 60_000);
    if (kind !== "30") { target.setHours(20, 0, 0, 0); if (kind === "tomorrow" || target.getTime() <= Date.now()) target.setDate(target.getDate() + 1); }
    const parts = localParts(target); setDate(parts.date); setTime(parts.time); setMode("later"); setCreated(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !scheduleValid) return;
    setBusy(true); setError(null);
    try {
      const startsAt = mode === "later" ? scheduledDate.toISOString() : undefined;
      const runtime = durationSeconds(selected.duration);
      if (!runtime) throw new Error("This title has no valid runtime. Retranscode it before creating a party.");
      const result = await createPartyRoom({ movie_id: selected.id, title: selected.title, starts_at: startsAt, duration_seconds: runtime });
      setCreated({ code: result.code, startsAt });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create the watch party."); } finally { setBusy(false); }
  }

  async function copy(value: string, kind: "code" | "link") { await navigator.clipboard.writeText(value); setCopied(kind); window.setTimeout(() => setCopied(null), 1600); }

  const poster = selected?.posterUrl || selected?.thumbnailUrl || selected?.backdropUrl;
  const video = selected?.mediaInfo?.video;
  const invitePath = created ? `/party?code=${created.code}` : "";

  return <section className={styles.studio}>
    <div className={styles.glow} />
    <header className={styles.header}><span className={styles.icon}><Film /></span><div><span className={styles.overline}>Private screening</span><h2>Host a Watch Party</h2><p>Choose a film, set the curtain time, and share one private code.</p></div><span className={styles.secure}><Radio /> Live room</span></header>
    <div className={styles.layout}>
      <div className={styles.library}>
        <div className={styles.sectionTitle}><span>Your ready titles</span><small>{movies.length} available</small></div>
        <div className={styles.movieTable} role="listbox" aria-label="Choose a movie">
          {!movies.length && <div className={styles.empty}>Finish transcoding a title to host a screening.</div>}
          {movies.map((movie) => { const artwork = movie.posterUrl || movie.thumbnailUrl || movie.backdropUrl; const info = movie.mediaInfo?.video; const active = movie.id === movieId; const partyState = partyStates.get(movie.id); return <button type="button" role="option" aria-selected={active} key={movie.id} className={active ? styles.movieActive : styles.movieRow} onClick={() => { setMovieId(movie.id); setCreated(null); }}><span className={styles.poster} style={artwork ? { backgroundImage: `url("${artwork}")` } : { backgroundImage: movie.gradient }} /><span className={styles.movieCopy}><b>{movie.title}</b><small>{[movie.year, movie.duration, info?.height ? `${info.height}p` : null].filter(Boolean).join(" · ")}</small></span><span className={styles.ready}>{partyState === "live" ? <><Radio /> Playing now</> : partyState === "scheduled" ? <><Clock3 /> Scheduled</> : <><Check /> Ready</>}</span><ChevronRight className={styles.chevron} /></button>; })}
        </div>
        {selected && <div className={styles.featured} style={poster ? { backgroundImage: `linear-gradient(90deg, rgba(11,11,20,.94), rgba(11,11,20,.48)), url("${poster}")` } : undefined}><span>Selected presentation</span><h3>{selected.title}</h3><p>{[selected.duration || "Runtime unavailable", video?.width && video?.height ? `${video.width} × ${video.height}` : "Adaptive HLS", video?.codec?.toUpperCase()].filter(Boolean).join("  ·  ")}</p></div>}
      </div>
      <form className={styles.scheduler} onSubmit={submit}>
        <div className={styles.sectionTitle}><span>Set the curtain time</span><small>{timezone}</small></div>
        <div className={styles.modeSwitch}><button type="button" className={mode === "now" ? styles.modeActive : ""} onClick={() => { setMode("now"); setCreated(null); }}><Play />Start now</button><button type="button" className={mode === "later" ? styles.modeActive : ""} onClick={() => { setMode("later"); setCreated(null); }}><CalendarDays />Schedule</button></div>
        {mode === "later" && <><div className={styles.dateGrid}><label><span>Date</span><div><CalendarDays /><input type="date" value={date} min={localParts(new Date()).date} onChange={(event) => { setDate(event.target.value); setCreated(null); }} /></div></label><label><span>Time</span><div><Clock3 /><input type="time" value={time} onChange={(event) => { setTime(event.target.value); setCreated(null); }} /></div></label></div><div className={styles.presets}><span>Quick presets</span><div><button type="button" onClick={() => applyPreset("30")}>In 30 min</button><button type="button" onClick={() => applyPreset("tonight")}>Tonight · 8 PM</button><button type="button" onClick={() => applyPreset("tomorrow")}>Tomorrow · 8 PM</button></div></div></>}
        <div className={scheduleValid ? styles.startPreview : styles.startError}><Sparkles /><div><small>{mode === "later" ? "Your premiere starts" : "Room opens immediately"}</small><strong>{scheduleValid ? exactStart : "Choose a future date and time"}</strong>{mode === "later" && scheduleValid && <span>Begins in {countdown(scheduledDate.getTime(), now)} · saved as UTC</span>}</div></div>
        <button className={styles.createButton} disabled={busy || !selected || !scheduleValid}>{busy ? <Loader2 className="animate-spin" /> : <Film />}{busy ? "Preparing theater…" : mode === "later" ? "Schedule Watch Party" : "Create Watch Party"}</button>
        {error && <p className={styles.error}>{error}</p>}
        {created && <div className={styles.success}><div><span>The theater is ready</span><strong>{created.code}</strong><small>{created.startsAt ? `Scheduled · ${exactStart}` : "Open now"}</small></div><div className={styles.successActions}><button type="button" onClick={() => void copy(created.code, "code")}>{copied === "code" ? <Check /> : <Copy />}{copied === "code" ? "Copied" : "Copy code"}</button><button type="button" onClick={() => void copy(`${window.location.origin}${invitePath}`, "link")}><Copy />{copied === "link" ? "Copied" : "Copy invite"}</button><a href={invitePath} target="_blank" rel="noreferrer"><ExternalLink />Open theater</a></div></div>}
      </form>
    </div>
  </section>;
}
