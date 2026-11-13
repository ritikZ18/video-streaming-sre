import { backendBase } from "./backend";
import { authHeader } from "./auth";

export type PartyRoom = {
  room_id: string;
  movie_id: string;
  title: string;
  state: "waiting" | "scheduled" | "live" | string;
  starts_at?: string;
  ends_at?: number;
  duration_seconds?: number;
  position_seconds: number;
  playing: boolean;
  version: number;
  server_time?: number;
  participants?: number;
  ready_participants?: number;
  participant_details?: { viewer_id: string; name: string; ready: boolean; joined_at: number; ip_hash: string; country: string; drift_ms: number; bitrate_kbps: number }[];
  recent_events?: { timestamp: number; type: string; viewer_id?: string; name?: string; ready?: boolean }[];
};

export type PartyMessage =
  | { type: "room_state"; room: PartyRoom }
  | { type: "presence"; name: string; count: number }
  | { type: "chat"; name: string; text: string }
  | { type: "ended"; ended_at?: number }
  | { type: "playback"; position_seconds: number; playing: boolean; version: number };

function gatewayBase(): string {
  return backendBase() ?? "http://localhost:8088";
}

export function relayMediaUrl(movieId: string): string {
  return `${gatewayBase()}/hls/${encodeURIComponent(movieId)}/master.m3u8`;
}

export function partyArtworkUrl(movieId: string): string {
  return `${gatewayBase()}/hls/${encodeURIComponent(movieId)}/thumbnail.jpg`;
}

export async function fetchPartyRoom(roomId: string): Promise<PartyRoom> {
  const response = await fetch(`${gatewayBase()}/api/party/rooms/${encodeURIComponent(roomId)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(response.status === 404 ? "This invite is no longer valid." : "Could not join this room.");
  return (await response.json()) as PartyRoom;
}

export async function joinPartyRoom(roomId: string): Promise<{ access_token: string; viewer_id: string; room: PartyRoom }> {
  const response = await fetch(`${gatewayBase()}/api/party/rooms/${encodeURIComponent(roomId)}/join`, { method: "POST" });
  if (!response.ok) throw new Error(response.status === 404 ? "This party code is invalid or expired." : "Could not enter this watch party.");
  const joined = await response.json();
  window.sessionStorage.setItem(`streamsre.party.token.${roomId}`, joined.access_token);
  return joined;
}

export function partyToken(roomId: string): string | null {
  return typeof window === "undefined" ? null : window.sessionStorage.getItem(`streamsre.party.token.${roomId}`);
}

export function partySocketUrl(roomId: string, name: string): string {
  const base = new URL(gatewayBase());
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = `/ws/party/${encodeURIComponent(roomId)}`;
  base.search = new URLSearchParams({ name }).toString();
  return base.toString();
}

export type PartyAdminStats = { rooms: PartyRoom[]; generated_at: number };
export async function fetchPartyAdminStats(): Promise<PartyAdminStats> {
  const response = await fetch(`${gatewayBase()}/api/party/admin/rooms`, { headers: authHeader(), cache: "no-store" });
  if (!response.ok) throw new Error("Could not load party telemetry.");
  return response.json();
}

export async function endPartyRoom(roomId: string): Promise<void> {
  const response = await fetch(`${gatewayBase()}/api/party/admin/rooms/${encodeURIComponent(roomId)}/end`, {
    method: "POST",
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(response.status === 401 ? "Admin sign-in expired." : "Could not end this watch party.");
}

export async function createPartyRoom(input: { movie_id: string; title: string; starts_at?: string; duration_seconds: number }): Promise<{ code: string; host_token: string; room: PartyRoom }> {
  const response = await fetch(`${gatewayBase()}/api/party/rooms`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(response.status === 401 ? "Admin sign-in expired." : "Could not create the watch party.");
  return response.json();
}
