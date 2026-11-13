import { backendBase } from "./backend";
import { authHeader } from "./auth";

export type PartyRoom = {
  room_id: string;
  movie_id: string;
  title: string;
  state: "waiting" | "scheduled" | "live" | string;
  starts_at?: string;
  position_seconds: number;
  playing: boolean;
  version: number;
};

export type PartyMessage =
  | { type: "room_state"; room: PartyRoom }
  | { type: "presence"; name: string; count: number }
  | { type: "chat"; name: string; text: string }
  | { type: "playback"; position_seconds: number; playing: boolean; version: number };

function gatewayBase(): string {
  return backendBase() ?? "http://localhost:8088";
}

export function relayMediaUrl(movieId: string): string {
  return `${gatewayBase()}/hls/${encodeURIComponent(movieId)}/master.m3u8`;
}

export async function fetchPartyRoom(roomId: string): Promise<PartyRoom> {
  const response = await fetch(`${gatewayBase()}/api/party/rooms/${encodeURIComponent(roomId)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(response.status === 404 ? "This invite is no longer valid." : "Could not join this room.");
  return (await response.json()) as PartyRoom;
}

export function partySocketUrl(roomId: string, name: string): string {
  const base = new URL(gatewayBase());
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = `/ws/party/${encodeURIComponent(roomId)}`;
  base.search = new URLSearchParams({ name }).toString();
  return base.toString();
}

export async function createPartyRoom(input: { movie_id: string; title: string; starts_at?: string }): Promise<{ code: string; host_token: string; room: PartyRoom }> {
  const response = await fetch(`${gatewayBase()}/api/party/rooms`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(response.status === 401 ? "Admin sign-in expired." : "Could not create the watch party.");
  return response.json();
}
