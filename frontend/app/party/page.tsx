"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CalendarClock,
  Check,
  ChevronDown,
  CircleHelp,
  Clapperboard,
  Clock3,
  Copy,
  Film,
  Hash,
  Headphones,
  LockKeyhole,
  MessageCircle,
  MicOff,
  MonitorPlay,
  Play,
  Radio,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
  Video,
  Wifi,
} from "lucide-react";
import { VideoPlayer } from "../../components/player/VideoPlayer";
import { getMovie, listMovies } from "../../lib/api";
import { initialMovies } from "../../data/movies";
import type { Movie } from "../../lib/types";
import "./party.css";

type ChatMessage = {
  id: number;
  name: string;
  message: string;
  time: string;
  color: "lavender" | "rose" | "mint";
  sample?: boolean;
};

const SAMPLE_CHAT: ChatMessage[] = [
  {
    id: 1,
    name: "Maya",
    message: "The theater is looking good. Popcorn ready? 🍿",
    time: "8:42",
    color: "rose",
    sample: true,
  },
  {
    id: 2,
    name: "Alex",
    message: "Calling dibs on the front row.",
    time: "8:43",
    color: "mint",
    sample: true,
  },
  {
    id: 3,
    name: "Maya",
    message: "That countdown is kind of cinematic.",
    time: "8:44",
    color: "rose",
    sample: true,
  },
];

function pad(number: number): string {
  return String(number).padStart(2, "0");
}

function toLocalInput(date: Date): string {
  return (
    String(date.getFullYear()) +
    "-" +
    pad(date.getMonth() + 1) +
    "-" +
    pad(date.getDate()) +
    "T" +
    pad(date.getHours()) +
    ":" +
    pad(date.getMinutes())
  );
}

function humanTime(iso: string, zone?: string): string {
  if (!iso) return "Choose a premiere time";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "Choose a premiere time";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
    ...(zone ? { timeZone: zone } : {}),
  }).format(when);
}

function countdownParts(seconds: number) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  return [
    { label: "DAYS", value: pad(days) },
    { label: "HOURS", value: pad(hours) },
    { label: "MINUTES", value: pad(minutes) },
    { label: "SECONDS", value: pad(remainingSeconds) },
  ];
}

function getBrowserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export default function PartyPage() {
  const [movie, setMovie] = useState<Movie>(initialMovies[0]);
  const [startsAt, setStartsAt] = useState("");
  const [scheduleInput, setScheduleInput] = useState("");
  const [now, setNow] = useState(0);
  const [localZone, setLocalZone] = useState("UTC");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dateError, setDateError] = useState("");
  const [isLive, setIsLive] = useState(false);
  const [ready, setReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activePanel, setActivePanel] = useState<"chat" | "people">("chat");
  const [messages, setMessages] = useState<ChatMessage[]>(SAMPLE_CHAT);
  const [draftMessage, setDraftMessage] = useState("");
  const chatEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const movieId = params.get("movieId");
    const candidate = params.get("at");
    const validStart = candidate && !Number.isNaN(Date.parse(candidate));
    const premiere = validStart
      ? new Date(candidate as string)
      : new Date(Date.now() + 46 * 60 * 1000);

    setStartsAt(premiere.toISOString());
    setScheduleInput(toLocalInput(premiere));
    setLocalZone(getBrowserZone());
    setNow(Date.now());

    let active = true;
    if (movieId) {
      const seeded = initialMovies.find((item) => item.id === movieId);
      if (seeded) setMovie(seeded);
      void getMovie(movieId)
        .then((item) => {
          if (active && item) setMovie(item);
        })
        .catch(() => {});
    } else {
      void listMovies()
        .then((items) => {
          const candidateMovie = items.find(
            (item) => item.status === "ready" && item.manifestUrl,
          );
          if (active && candidateMovie) setMovie(candidateMovie);
        })
        .catch(() => {});
    }

    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, activePanel]);

  const remaining = useMemo(() => {
    if (!startsAt || !now) return 0;
    return Math.max(0, Math.ceil((new Date(startsAt).getTime() - now) / 1000));
  }, [startsAt, now]);

  const clock = countdownParts(remaining);
  const hasMedia = Boolean(movie.manifestUrl && movie.status !== "processing");
  const showtime = Boolean(startsAt) && remaining === 0;
  const scheduledLabel = humanTime(startsAt);
  const statusLabel = isLive ? "LIVE PREVIEW" : showtime ? "READY TO START" : "PREMIERE SCHEDULED";

  function saveSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const candidate = new Date(scheduleInput);
    if (
      !scheduleInput ||
      Number.isNaN(candidate.getTime()) ||
      candidate.getTime() <= Date.now() + 5000
    ) {
      setDateError("Choose a future date and time in your local timezone.");
      return;
    }
    setStartsAt(candidate.toISOString());
    setIsLive(false);
    setDateError("");
    setSettingsOpen(false);
  }

  function sendChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draftMessage.trim().slice(0, 400);
    if (!message) return;
    setMessages((items) => [
      ...items,
      {
        id: Date.now(),
        name: "You",
        message,
        time: new Intl.DateTimeFormat("en-US", {
          hour: "numeric",
          minute: "2-digit",
        }).format(new Date()),
        color: "lavender",
      },
    ]);
    setDraftMessage("");
  }

  async function copyPreviewLink() {
    const url = new URL("/party", window.location.origin);
    url.searchParams.set("movieId", movie.id);
    if (startsAt) url.searchParams.set("at", startsAt);
    try {
      await navigator.clipboard.writeText(url.toString());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
      window.prompt("Copy this preview URL:", url.toString());
    }
  }

  return (
    <div className="party-shell">
      <nav className="party-rail" aria-label="Main navigation">
        <Link className="party-rail-logo" href="/" aria-label="StreamSRE home">
          <Play size={20} fill="currentColor" />
        </Link>
        <span className="party-rail-line" />
        <Link href="/" className="party-rail-item" title="Home" aria-label="Home">
          <Film size={21} />
        </Link>
        <Link
          href="/party"
          className="party-rail-item party-rail-item-active"
          title="Watch Party"
          aria-label="Watch Party"
          aria-current="page"
        >
          <Users size={21} />
        </Link>
        <Link href="/browse" className="party-rail-item" title="Library" aria-label="Library">
          <Clapperboard size={21} />
        </Link>
        <div className="party-rail-spacer" />
        <Link href="/sre" className="party-rail-item" title="SRE Dashboard" aria-label="SRE Dashboard">
          <Wifi size={21} />
        </Link>
        <Link href="/admin" className="party-rail-avatar" title="Admin" aria-label="Admin">
          S
        </Link>
      </nav>

      <aside className="party-channels" aria-label="Watch party channels">
        <div className="party-workspace">
          <div className="party-workspace-brand">
            <span className="party-workspace-emoji">✦</span>
            <span>StreamSRE Nights</span>
          </div>
          <ChevronDown size={16} />
        </div>
        <div className="party-channel-scroll">
          <div className="party-mini-poster" style={{ backgroundImage: movie.thumbnailUrl ? "url(" + JSON.stringify(movie.thumbnailUrl) + ")" : movie.gradient }}>
            <div className="party-mini-poster-shade">
              <span className="party-mini-pill"><span className="party-dot" /> NEXT SCREENING</span>
              <strong>{movie.title}</strong>
              <span>{movie.genre} • {movie.year}</span>
            </div>
          </div>

          <div className="party-channel-heading"><ChevronDown size={12} /> THEATER CHANNELS</div>
          <a className="party-channel party-channel-selected" href="#theater">
            <Hash size={19} /> <span>watch-party</span>
            <span className="party-channel-unread" />
          </a>
          <button className="party-channel" type="button" onClick={() => setActivePanel("chat")}>
            <MessageCircle size={18} /> <span>movie-chat</span>
          </button>
          <button className="party-channel" type="button" onClick={() => setSettingsOpen(true)}>
            <CalendarClock size={18} /> <span>premiere-planner</span>
          </button>

          <div className="party-channel-heading party-heading-space"><ChevronDown size={12} /> VOICE CHANNELS</div>
          <div className="party-channel party-channel-muted" title="Voice is a visual placeholder until WebRTC is connected">
            <Headphones size={18} /> <span>Cinema lounge</span>
            <span className="party-soon">SOON</span>
          </div>

          <div className="party-sidebar-info">
            <div className="party-sidebar-info-icon"><Sparkles size={16} /></div>
            <strong>A whole theater, one link.</strong>
            <span>Make movie night feel like an event.</span>
          </div>
        </div>
        <div className="party-identity">
          <div className="party-identity-avatar">Y<span /></div>
          <div className="party-identity-name"><strong>You</strong><small>Local preview</small></div>
          <span className="party-identity-lock" title="Local UI prototype"><LockKeyhole size={15} /></span>
        </div>
      </aside>

      <main className="party-main" id="theater">
        <header className="party-topbar">
          <div className="party-topbar-left">
            <span className="party-hash"><Hash size={20} /></span>
            <div>
              <strong>watch-party</strong>
              <small>A private screening room for everyone</small>
            </div>
          </div>
          <div className="party-topbar-actions">
            <span className="party-preview-badge"><span /> UI PREVIEW</span>
            <button type="button" className="party-header-icon" onClick={() => setSettingsOpen(!settingsOpen)} aria-label="Premiere settings" title="Premiere settings"><Settings2 size={18} /></button>
            <button type="button" className="party-invite" onClick={copyPreviewLink}>
              {copied ? <Check size={16} /> : <Copy size={16} />}
              <span>{copied ? "Copied" : "Copy preview link"}</span>
            </button>
          </div>
        </header>

        <div className="party-content-scroll">
          <div className="party-content-head">
            <div>
              <p className="party-overline"><span className="party-overline-star">✳</span> NOW IN THE THEATER</p>
              <h1>Movie night, <em>together.</em></h1>
              <p>A proper screening room. Big picture, great company, zero distractions.</p>
            </div>
            <div className="party-quick-info">
              <div className="party-quick-icon"><Users size={17} /></div>
              <strong>01</strong>
              <span>local viewer</span>
            </div>
          </div>

          <div className="party-stage">
            <div className="party-stage-top">
              <div className="party-stage-title">
                <span className={isLive ? "party-status-live" : "party-status-planned"}>
                  <span /> {statusLabel}
                </span>
                <span className="party-stage-film">{movie.title}</span>
              </div>
              <span className="party-stage-meta">1080p-ready UI <span>·</span> HOST PREVIEW</span>
            </div>

            {isLive ? (
              <div className="party-video-shell">
                {hasMedia ? (
                  <VideoPlayer
                    src={movie.manifestUrl ?? null}
                    title={movie.title}
                    poster={movie.thumbnailUrl}
                    contentId={movie.id}
                    subtitleTracks={movie.subtitleTracks ?? []}
                  />
                ) : (
                  <div className="party-video-empty">
                    <Video size={42} />
                    <h2>This movie is still processing.</h2>
                    <p>Finish uploading and transcoding before starting the screening.</p>
                    <Link href="/admin" className="party-primary-button">Open upload studio</Link>
                  </div>
                )}
              </div>
            ) : (
              <div className="party-countdown-stage" style={{ backgroundImage: movie.thumbnailUrl ? "linear-gradient(125deg,rgba(16,16,37,.94),rgba(21,13,43,.55)),url(" + JSON.stringify(movie.thumbnailUrl) + ")" : movie.gradient }}>
                <div className="party-stage-stars" aria-hidden="true" />
                <div className="party-orbit party-orbit-one" aria-hidden="true" />
                <div className="party-orbit party-orbit-two" aria-hidden="true" />
                <div className="party-countdown-inner">
                  <div className="party-premiere-tag"><Sparkles size={13} /> YOUR PRIVATE PREMIERE</div>
                  <p className="party-countdown-heading">{showtime ? "It’s showtime." : "The magic starts in"}</p>
                  <div className="party-clock" role="timer" aria-label="Time until the premiere">
                    {clock.map((item, index) => (
                      <div className="party-clock-group" key={item.label}>
                        <div className="party-clock-box">{item.value}</div>
                        <span>{item.label}</span>
                        {index < clock.length - 1 && <b aria-hidden="true">:</b>}
                      </div>
                    ))}
                  </div>
                  <p className="party-start-label"><Clock3 size={14} /> {scheduledLabel}</p>
                  <div className="party-countdown-actions">
                    <button type="button" className="party-ready-button" onClick={() => setReady(!ready)}>
                      {ready ? <Check size={17} /> : <ShieldCheck size={17} />}
                      {ready ? "You're ready!" : "I'm ready"}
                    </button>
                    <button type="button" className="party-outline-button" onClick={() => setIsLive(true)}>
                      <Play size={16} fill="currentColor" /> Start local preview
                    </button>
                  </div>
                  <span className="party-stage-note">
                    Demo countdown runs on your browser clock. Playback is not synchronized with guests yet.
                  </span>
                </div>
              </div>
            )}

            <div className="party-stage-footer">
              <div className="party-film-details">
                <div className="party-film-icon"><Film size={18} /></div>
                <div><strong>{movie.title}</strong><span>{movie.genre} <i /> {movie.year} <i /> {movie.duration || "Movie screening"}</span></div>
              </div>
              <div className="party-stage-footer-actions">
                {isLive && <button type="button" className="party-mini-action" onClick={() => setIsLive(false)}><Clock3 size={15} /> Back to lobby</button>}
                <button type="button" className="party-mini-action" onClick={() => setSettingsOpen(!settingsOpen)}><CalendarClock size={15} /> Schedule</button>
              </div>
            </div>
          </div>

          <div className="party-bottom-grid">
            <section className="party-info-card">
              <div className="party-info-top"><span className="party-info-icon"><Radio size={19}/></span><span className="party-info-state">PREVIEW MODE</span></div>
              <h2>Your screening, your rules.</h2>
              <p>Set a start time, pick a movie, and invite the whole group. The next step is connecting the realtime room service for synchronized playback.</p>
              <div className="party-info-steps"><span><Check size={14} /> Movie selected</span><span><Check size={14}/> Local timer</span><span className="party-step-pending"><CircleHelp size={14}/> Realtime backend pending</span></div>
            </section>
            <section className="party-time-card">
              <div className="party-time-heading"><CalendarClock size={17} /><span>Across time zones</span></div>
              <div className="party-time-row"><span>YOUR TIME <small>{localZone}</small></span><strong>{humanTime(startsAt)}</strong></div>
              <div className="party-time-row"><span>NEW YORK <small>America/New_York</small></span><strong>{humanTime(startsAt, "America/New_York")}</strong></div>
              <div className="party-time-row"><span>LOS ANGELES <small>America/Los_Angeles</small></span><strong>{humanTime(startsAt, "America/Los_Angeles")}</strong></div>
              <small className="party-time-footnote">EST/EDT and PST/PDT are calculated automatically, including daylight saving changes.</small>
            </section>
          </div>
        </div>

        {settingsOpen && (
          <div className="party-settings-scrim" onClick={() => setSettingsOpen(false)}>
            <section className="party-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="party-settings-title" onClick={(e) => e.stopPropagation()}>
              <div className="party-dialog-top">
                <span className="party-dialog-icon"><CalendarClock size={22}/></span>
                <button type="button" onClick={() => setSettingsOpen(false)} aria-label="Close settings" className="party-dialog-close">×</button>
              </div>
              <p className="party-overline">PREMIERE PLANNER</p>
              <h2 id="party-settings-title">Set the scene.</h2>
              <p>Choose the screening date in your own timezone. Every viewer sees the corresponding local start time.</p>
              <form onSubmit={saveSchedule}>
                <label htmlFor="party-date">Premiere date & time</label>
                <input
                  id="party-date"
                  type="datetime-local"
                  value={scheduleInput}
                  onChange={(e) => { setScheduleInput(e.target.value); setDateError(""); }}
                  required
                />
                <div className="party-dialog-tz"><Clock3 size={15} /> Interpreted as {localZone}, then stored as UTC</div>
                {dateError && <p className="party-date-error" role="alert">{dateError}</p>}
                <button type="submit" className="party-dialog-save">Save premiere time <Check size={17}/></button>
              </form>
              <p className="party-dialog-disclaimer">Local UI prototype only. The final implementation will save the schedule on the party server.</p>
            </section>
          </div>
        )}
      </main>

      <aside className="party-chat-pane" aria-label="Party chat and participants">
        <div className="party-chat-top">
          <div className="party-chat-title"><MessageCircle size={19}/><strong>Room activity</strong></div>
          <div className="party-chat-tabs" role="tablist" aria-label="Room panels">
            <button type="button" role="tab" aria-selected={activePanel === "chat"} className={activePanel === "chat" ? "active" : ""} onClick={() => setActivePanel("chat")}>Chat</button>
            <button type="button" role="tab" aria-selected={activePanel === "people"} className={activePanel === "people" ? "active" : ""} onClick={() => setActivePanel("people")}>People</button>
          </div>
        </div>

        {activePanel === "chat" ? (
          <>
            <div className="party-chat-messages" role="log" aria-label="Local preview chat messages">
              <div className="party-chat-welcome">
                <span className="party-chat-welcome-icon"><MessageCircle size={24}/></span>
                <h3>Movie night starts here.</h3>
                <p>Save the best reactions for the chat. These messages are examples shown for the UI preview.</p>
              </div>
              <div className="party-chat-separator"><span>SAMPLE CONVERSATION</span></div>
              {messages.map((entry) => (
                <div className="party-message" key={entry.id}>
                  <div className={"party-message-avatar " + entry.color}>{entry.name.charAt(0)}</div>
                  <div className="party-message-body">
                    <div className="party-message-name"><strong>{entry.name}</strong><span>{entry.time}</span>{entry.sample && <small>demo</small>}</div>
                    <p>{entry.message}</p>
                  </div>
                </div>
              ))}
              <div ref={chatEnd} />
            </div>
            <form className="party-chat-composer" onSubmit={sendChat}>
              <div className="party-compose-field">
                <input
                  aria-label="Message in local chat preview"
                  placeholder="Message #watch-party"
                  value={draftMessage}
                  maxLength={400}
                  onChange={(e) => setDraftMessage(e.target.value)}
                />
                <button type="submit" disabled={!draftMessage.trim()} aria-label="Send preview message"><Send size={17}/></button>
              </div>
              <small>Messages stay in this browser tab. Live chat needs the party service.</small>
            </form>
          </>
        ) : (
          <div className="party-members">
            <span className="party-members-heading">CONNECTED HERE — 1</span>
            <div className="party-member"><span className="party-member-avatar">Y<i/></span><div><strong>You <span>HOST PREVIEW</span></strong><small>Viewing locally</small></div></div>
            <div className="party-members-divider" />
            <span className="party-members-heading">SAMPLE ROSTER (NOT ONLINE)</span>
            <div className="party-member party-member-muted"><span className="party-member-avatar rose">M</span><div><strong>Maya</strong><small>Example participant</small></div></div>
            <div className="party-member party-member-muted"><span className="party-member-avatar mint">A</span><div><strong>Alex</strong><small>Example participant</small></div></div>
            <div className="party-members-tip"><ShieldCheck size={17}/><span>Actual presence, roles, and permissions will come from the secure room backend.</span></div>
          </div>
        )}

        <div className="party-voice-panel">
          <div className="party-voice-label"><span><Headphones size={17}/> CINEMA LOUNGE</span><span>PLANNED</span></div>
          <div className="party-voice-body">
            <div className="party-voice-avatars"><span>Y</span><span>M</span><span>A</span></div>
            <div><strong>Hang out while you watch</strong><small>WebRTC voice channel coming later</small></div>
          </div>
          <div className="party-voice-actions">
            <button type="button" disabled title="Voice is not connected in the UI preview"><MicOff size={16}/> Mic unavailable</button>
            <button type="button" disabled title="Voice is not connected in the UI preview"><Headphones size={16}/> Join voice</button>
          </div>
        </div>
      </aside>
    </div>
  );
}
