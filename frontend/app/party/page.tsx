"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  Check,
  Copy,
  Loader2,
  MessageCircle,
  Send,
  ShieldCheck,
  Users,
  Wifi,
  WifiOff,
} from "lucide-react";
import { VideoPlayer } from "../../components/player/VideoPlayer";
import { fetchPartyRoom, partySocketUrl, relayMediaUrl, type PartyMessage, type PartyRoom } from "../../lib/party";
import styles from "./party.module.css";

type ChatMessage = { id: number; name: string; text: string; mine?: boolean };

export default function PartyPage() {
  const [room, setRoom] = useState<PartyRoom | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [people, setPeople] = useState(1);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [name, setName] = useState("Guest");
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const socketRef = useRef<WebSocket | null>(null);
  const chatId = useRef(0);

  const query = useMemo(() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    return { roomId: params.get("room"), inviteToken: params.get("invite") };
  }, []);

  useEffect(() => {
    if (!query?.roomId || !query.inviteToken) {
      setError("This theater link is missing a room or invite token.");
      setLoading(false);
      return;
    }
    const storedName = window.localStorage.getItem("streamsre.party.name");
    const guestName = storedName?.trim() || `Guest ${Math.floor(Math.random() * 90 + 10)}`;
    setName(guestName);

    let active = true;
    void fetchPartyRoom(query.roomId, query.inviteToken)
      .then((loadedRoom) => {
        if (!active) return;
        setRoom(loadedRoom);
        const socket = new WebSocket(partySocketUrl(query.roomId!, query.inviteToken!, guestName));
        socketRef.current = socket;
        socket.onopen = () => setConnected(true);
        socket.onclose = () => setConnected(false);
        socket.onerror = () => setConnected(false);
        socket.onmessage = (event) => {
          const message = JSON.parse(event.data) as PartyMessage;
          if (message.type === "room_state") setRoom(message.room);
          if (message.type === "presence") setPeople(message.count);
          if (message.type === "chat") {
            setChat((current) => [...current, { id: chatId.current++, name: message.name, text: message.text }].slice(-60));
          }
        };
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not join this room."))
      .finally(() => setLoading(false));

    return () => {
      active = false;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [query]);

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

  if (loading) {
    return <div className={styles.loading}><Loader2 className="h-6 w-6 animate-spin" /> Entering the theater...</div>;
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

  const syncLabel = room.playing ? "Synchronized playback" : "Waiting for the host";
  const premiereMs = room.starts_at ? Math.max(0, new Date(room.starts_at).getTime() - now) : 0;
  const premiereSeconds = Math.floor(premiereMs / 1000);
  const premiereParts = {
    days: Math.floor(premiereSeconds / 86400),
    hours: Math.floor((premiereSeconds % 86400) / 3600),
    minutes: Math.floor((premiereSeconds % 3600) / 60),
    seconds: premiereSeconds % 60,
  };

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <button type="button" className={styles.backButton} onClick={() => window.history.back()} aria-label="Leave theater"><ArrowLeft className="h-4 w-4" /> Exit theater</button>
        <div className={styles.brand}><span className={styles.brandMark}>S</span><span>StreamSRE <b>/ Theater</b></span></div>
        <div className={styles.topActions}>
          <span className={connected ? styles.livePill : styles.offlinePill}><span />{connected ? "Live" : "Reconnecting"}</span>
          <button type="button" className={styles.iconButton} onClick={copyInvite} title="Copy invite link">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</button>
        </div>
      </header>

      <section className={styles.theaterGrid}>
        <div className={styles.stageColumn}>
          <div className={styles.eyebrow}><span className={styles.liveDot} /> Private watch party <span className={styles.divider} /> {room.state === "scheduled" ? "Premiere scheduled" : "Room active"}</div>
          <div className={styles.playerFrame}>
            <VideoPlayer src={relayMediaUrl(room.movie_id)} title={room.title} contentId={room.movie_id} />
          </div>
          <div className={styles.titleRow}>
            <div>
              <p className={styles.kicker}>{room.state === "scheduled" ? "YOUR PRIVATE PREMIERE" : "NOW PLAYING"}</p>
              <h1>{room.title}</h1>
              {room.state === "scheduled" && premiereMs > 0 ? (
                <div className={styles.premiereCountdown} aria-label="Premiere countdown">
                  <span>{String(premiereParts.days).padStart(2, "0")}<small>days</small></span>
                  <b>:</b>
                  <span>{String(premiereParts.hours).padStart(2, "0")}<small>hours</small></span>
                  <b>:</b>
                  <span>{String(premiereParts.minutes).padStart(2, "0")}<small>min</small></span>
                  <b>:</b>
                  <span>{String(premiereParts.seconds).padStart(2, "0")}<small>sec</small></span>
                </div>
              ) : <p className={styles.subtitle}>Relay stream · room {room.room_id}</p>}
            </div>
            <div className={styles.syncBadge}><ShieldCheck className="h-4 w-4" /><span>{syncLabel}<small>Host clock is authoritative</small></span></div>
          </div>
          <div className={styles.statsStrip}><div><strong><Users className="h-4 w-4" />{people}</strong><span>watching now</span></div><div><strong><Wifi className="h-4 w-4" />1080p</strong><span>adaptive relay</span></div><div><strong>24 ms</strong><span>room latency</span></div></div>
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