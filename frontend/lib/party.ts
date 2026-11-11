import { backendBase } from "./backend";

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
  return `${gatewayBase()}/relay/${encodeURIComponent(movieId)}/master.m3u8`;
}

export async function fetchPartyRoom(roomId: string, inviteToken: string): Promise<PartyRoom> {
  const params = new URLSearchParams({ invite_token: inviteToken });
  const response = await fetch(`${gatewayBase()}/api/party/rooms/${encodeURIComponent(roomId)}?${params}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(response.status === 404 ? "This invite is no longer valid." : "Could not join this room.");
  return (await response.json()) as PartyRoom;
}

export function partySocketUrl(roomId: string, inviteToken: string, name: string): string {
  const base = new URL(gatewayBase());
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = `/ws/party/${encodeURIComponent(roomId)}`;
  base.search = new URLSearchParams({ invite_token: inviteToken, name }).toString();
  return base.toString();
}