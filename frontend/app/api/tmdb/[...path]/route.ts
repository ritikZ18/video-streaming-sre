import { NextResponse } from "next/server";

// Server-side TMDB proxy. The API key lives ONLY here (server runtime env) and
// is never sent to the browser. The client (lib/tmdb.ts) calls /api/tmdb/<path>
// and this handler forwards it to api.themoviedb.org with the key attached.
const KEY = process.env.TMDB_API_KEY ?? "";
const BASE = "https://api.themoviedb.org/3";

export const dynamic = "force-dynamic";

// `context` is typed `unknown` and the params awaited so this compiles under
// both Next 14 (sync params) and Next 15 (params is a Promise).
export async function GET(request: Request, context: unknown) {
  if (!KEY) {
    return NextResponse.json({ error: "TMDB not configured" }, { status: 503 });
  }
  const { params } = context as {
    params: { path?: string[] } | Promise<{ path?: string[] }>;
  };
  const resolved = await params;
  const path = (resolved?.path ?? []).join("/");
  const qs = new URLSearchParams(new URL(request.url).searchParams);
  qs.set("api_key", KEY);
  if (!qs.has("language")) qs.set("language", "en-US");

  try {
    const res = await fetch(`${BASE}/${path}?${qs.toString()}`, {
      // cache TMDB responses server-side for an hour (catalog changes slowly)
      next: { revalidate: 3600 },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "TMDB fetch failed" }, { status: 502 });
  }
}
