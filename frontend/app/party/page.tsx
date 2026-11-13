"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  CalendarClock,
  Check,
  Copy,
  Loader2,
  MessageCircle,
  Send,
  ShieldCheck,
  Users,
  Wifi,
  WifiOff,
  Sparkles,
} from "lucide-react";
import { VideoPlayer } from "../../components/player/VideoPlayer";
import { joinPartyRoom, partyArtworkUrl, partySocketUrl, relayMediaUrl, type PartyMessage, type PartyRoom } from "../../lib/party";
import styles from "./party.module.css";

type ChatMessage = { id: number; name: string; text: string; mine?: boolean };

export default function PartyPage() {
  const [room, setRoom] = useState<PartyRoom | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [people, setPeople] = useState(1);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [name, setName] = useState("Guest");
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [codeInput, setCodeInput] = useState("");
  const [ready, setReady] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const chatId = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const query = useMemo(() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    return { roomId: params.get("code") ?? params.get("room") };
  }, []);

  useEffect(() => {
    if (!query?.roomId) {
      setLoading(false);
      return;
    }
    const storedName = window.localStorage.getItem("streamsre.party.name");
    const guestName = storedName?.trim() || `Guest ${Math.floor(Math.random() * 90 + 10)}`;
    setName(guestName);

    let active = true;
    let attempt = 0;
    const connect = (token: string) => {
      if (!active) return;
      setConnectionAttempt(attempt);
      // Carry the session as a WebSocket subprotocol instead of in the URL so
      // reverse-proxy access logs never persist viewer credentials.
      const socket = new WebSocket(partySocketUrl(query.roomId!, guestName), ["party-v1", token]);
      socketRef.current = socket;
      socket.onopen = () => { attempt = 0; setConnectionAttempt(0); setConnected(true); };
      socket.onclose = () => {
        setConnected(false);
        if (!active) return;
        attempt += 1;
        setConnectionAttempt(attempt);
        reconnectTimer.current = setTimeout(() => connect(token), Math.min(10_000, 500 * 2 ** attempt));
      };
      socket.onerror = () => setConnected(false);
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as PartyMessage;
        if (message.type === "room_state") { setRoom(message.room); setPeople(message.room.participants ?? 1); }
        if (message.type === "presence") setPeople(message.count);
        if (message.type === "ended") setRoom((current) => current ? { ...current, state: "ended", playing: false } : current);
        if (message.type === "chat") setChat((current) => [...current, { id: chatId.current++, name: message.name, text: message.text }].slice(-60));
      };
    };
    void joinPartyRoom(query.roomId)
      .then((joined) => {
        if (!active) return;
        setRoom(joined.room);
        setAccessToken(joined.access_token);
        connect(joined.access_token);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not join this room."))
      .finally(() => setLoading(false));

    return () => {
      active = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [query]);

  function joinWithCode(event: FormEvent) {
    event.preventDefault();
    const code = codeInput.replace(/\D/g, "").slice(0, 10);
    if (code.length !== 10) return;
    window.location.assign(`/party?code=${code}`);
  }

  useEffect(() => {
    if (room?.state !== "scheduled" || !room.starts_at) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [room?.state, room?.starts_at]);

  function sendChat(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim().slice(0, 1000);
    if (!text || socketRef.current?.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(JSON.stringify({ type: "chat", text }));
    setDraft("");
  }

  async function copyInvite() {
    await navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  function toggleReady() {
    const next = !ready;
    setReady(next);
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: "ready", ready: next }));
  }

  if (loading) {
    return <div className={styles.loading}><Loader2 className="h-6 w-6 animate-spin" /> Entering the theater...</div>;
  }

  if (!query?.roomId) {
    return (
      <main className={styles.errorPage}>
        <form className={styles.errorPanel} onSubmit={joinWithCode}>
          <ShieldCheck className="h-6 w-6 text-indigo-300" />
          <h1>Join a watch party</h1>
          <p>Enter the 10-digit code shared by the host.</p>
          <input
            value={codeInput}
            onChange={(event) => setCodeInput(event.target.value.replace(/\D/g, "").slice(0, 10))}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="0000000000"
            aria-label="Watch party code"
            className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-center font-mono text-xl tracking-[0.25em] text-white outline-none focus:border-indigo-400"
          />
          <button type="submit" className={styles.primaryButton} disabled={codeInput.length !== 10}>Join theater</button>
        </form>
      </main>
    );
  }

  if (error || !room) {
    return (
      <main className={styles.errorPage}>
        <div className={styles.errorPanel}>
          <WifiOff className="h-6 w-6 text-rose-300" />
          <h1>Invitation unavailable</h1>
          <p>{error ?? "This room could not be found."}</p>
          <button type="button" className={styles.primaryButton} onClick={() => window.history.back()}><ArrowLeft className="h-4 w-4" /> Go back</button>
        </div>
      </main>
    );
  }

  if (room.state === "ended") {
    return (
      <main className={styles.errorPage}>
        <div className={styles.errorPanel}>
          <ShieldCheck className="h-6 w-6 text-indigo-300" />
          <h1>The screening has ended</h1>
          <p>The host closed this watch party. Its playback access is no longer valid.</p>
          <button type="button" className={styles.primaryButton} onClick={() => window.location.assign("/party")}>
            Enter another code
          </button>
        </div>
      </main>
    );
  }

  const syncLabel = connected ? "Party room connected" : "Reconnecting";
  const premiereMs = room.starts_at ? Math.max(0, new Date(room.starts_at).getTime() - now) : 0;
  const premiereSeconds = Math.floor(premiereMs / 1000);
  const premiereParts = {
    days: Math.floor(premiereSeconds / 86400),
    hours: Math.floor((premiereSeconds % 86400) / 3600),
    minutes: Math.floor((premiereSeconds % 3600) / 60),
    seconds: premiereSeconds % 60,
  };
  const exactPremiere = room.starts_at ? new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(new Date(room.starts_at)) : "";
  const scheduled = room.state === "scheduled" && premiereMs > 0;

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <button type="button" className={styles.backButton} onClick={() => window.history.back()} aria-label="Leave theater"><ArrowLeft className="h-4 w-4" /> Exit theater</button>
        <div className={styles.brand}><span className={styles.brandMark}>S</span><span>StreamSRE <b>/ Theater</b></span></div>
        <div className={styles.topActions}>
          <span className={connected ? styles.livePill : styles.offlinePill}><span />{connected ? "Connected" : connectionAttempt ? `Reconnecting · ${connectionAttempt}` : "Connecting"}</span>
          <button type="button" className={styles.iconButton} onClick={copyInvite} title="Copy invite link">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</button>
        </div>
      </header>

      <section className={styles.theaterGrid}>
        <div className={styles.stageColumn}>
          <div className={styles.eyebrow}><span className={styles.liveDot} /> Private watch party <span className={styles.divider} /> {room.state === "scheduled" ? "Premiere scheduled" : "Room active"}</div>
          <div className={scheduled ? styles.lobbyFrame : styles.playerFrame}>
            {scheduled ? (
              <div className={`${styles.premiereLobby} ${premiereSeconds <= 10 ? styles.finalCountdown : ""}`}>
                <div className={styles.lobbyArtwork} style={{ backgroundImage: `url("${partyArtworkUrl(room.movie_id)}")` }} />
                <div className={styles.lobbyShade} />
                <div className={styles.lobbyContent}>
                  <p className={styles.lobbyKicker}><Sparkles /> Your private premiere</p>
                  <h1>The screening begins in</h1>
                  <div className={styles.heroCountdown} aria-label={`${premiereParts.days} days, ${premiereParts.hours} hours, ${premiereParts.minutes} minutes, ${premiereParts.seconds} seconds`}>
                    {[{ value: premiereParts.days, label: "Days" }, { value: premiereParts.hours, label: "Hours" }, { value: premiereParts.minutes, label: "Minutes" }, { value: premiereParts.seconds, label: "Seconds" }].map((part, index) => <div className={styles.countUnit} key={part.label}><strong>{String(part.value).padStart(2, "0")}</strong><span>{part.label}</span>{index < 3 && <i />}</div>)}
                  </div>
                  <p className={styles.exactTime}><CalendarClock /> {exactPremiere}<span>· Your local time</span></p>
                  <div className={styles.lobbyActions}><button type="button" className={ready ? styles.readyButtonActive : styles.readyButton} onClick={toggleReady}>{ready ? <Check /> : <ShieldCheck />}{ready ? "You're ready" : "I'm ready"}</button><button type="button" className={styles.copyButton} onClick={copyInvite}>{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy invite"}</button></div>
                  <div className={styles.lobbyMeta}><span><Users />{people} connected · {room.ready_participants ?? 0} ready</span><span><Wifi />Stream ready</span><span>Code {room.room_id}</span></div>
                </div>
              </div>
            ) : (
              <VideoPlayer src={relayMediaUrl(room.movie_id)} title={room.title} contentId={room.movie_id} requestHeaders={accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined} broadcastLocked broadcastStartMs={room.starts_at ? new Date(room.starts_at).getTime() : null} onBroadcastHeartbeat={({ driftMs, bitrateKbps }) => { if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: "heartbeat", drift_ms: driftMs, bitrate_kbps: bitrateKbps })); }} />
            )}
          </div>
          <div className={styles.titleRow}>
            <div>
              <p className={styles.kicker}>{room.state === "scheduled" ? "YOUR PRIVATE PREMIERE" : "NOW PLAYING"}</p>
              <h1>{room.title}</h1>
              <p className={styles.subtitle}>{scheduled ? `Premiere scheduled · ${exactPremiere}` : `Private stream · code ${room.room_id}`}</p>
            </div>
            <div className={styles.syncBadge}><ShieldCheck className="h-4 w-4" /><span>{syncLabel}<small>Chat and room state are live</small></span></div>
          </div>
          <div className={styles.statsStrip}><div><strong><Users className="h-4 w-4" />{people}</strong><span>watching now</span></div><div><strong><Wifi className="h-4 w-4" />Adaptive</strong><span>Cloudflare tunnel</span></div><div><strong>{room.room_id}</strong><span>party code</span></div></div>
        </div>

        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}><div><p className={styles.kicker}>THEATER LOUNGE</p><h2>Party chat</h2></div><span className={styles.peopleCount}><Users className="h-4 w-4" /> {people}</span></div>
          <div className={styles.peopleLine}><span className={styles.avatar}>Y</span><span><b>{name}</b><small>Watching from this device</small></span><span className={styles.youTag}>YOU</span></div>
          <div className={styles.chatLog} aria-live="polite">
            {!chat.length && <div className={styles.emptyChat}><MessageCircle className="h-5 w-5" /><p>The room is quiet.</p><span>Say hello when the lights go down.</span></div>}
            {chat.map((message) => <div className={styles.chatMessage} key={message.id}><span className={styles.avatar}>{message.name.slice(0, 1).toUpperCase()}</span><div><div><b>{message.name}</b><small>now</small></div><p>{message.text}</p></div></div>)}
          </div>
          <form className={styles.composer} onSubmit={sendChat}><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Say something..." aria-label="Chat message" maxLength={1000} /><button type="submit" aria-label="Send message"><Send className="h-4 w-4" /></button></form>
          <div className={styles.loungeFooter}><span className={styles.micDot} /> Voice channel ready <button type="button" onClick={copyInvite}>{copied ? "Copied" : "Invite friends"}</button></div>
        </aside>
      </section>
    </main>
  );
}
