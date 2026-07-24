"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Check, Loader2, Play, Trash2 } from "lucide-react";
import { getJobStatus, uploadVideo, MAX_UPLOAD_MB } from "../../lib/api";
import { parseMediaFilename } from "../../lib/mediaName";
import type { Genre, Rating, Tag } from "../../lib/types";

type ItemStatus = "queued" | "uploading" | "transcoding" | "ready" | "error";

type QItem = {
  id: string;
  file: File;
  title: string;
  year: string;
  status: ItemStatus;
  uploadPct: number; // 0-100 while uploading
  progress: number; // 0-100 transcode
  stage: string | null;
  jobId: string | null;
  streamUrl: string | null;
  error?: string;
};

type UploadQueueProps = {
  /** Files accumulated by the dropzone. New files are appended to the queue. */
  files: File[];
  onClear: () => void;
};

const GENRES: Genre[] = ["Action", "Sci-Fi", "Drama", "Comedy", "Documentary"];
const RATINGS: Rating[] = ["G", "PG", "PG-13", "R", "NC-17"];
const TAGS: Exclude<Tag, null>[] = ["Trending", "New Release", "Award Winner", "Editor's Pick", "Popular"];

const keyFor = (f: File) => `${f.name}::${f.size}::${f.lastModified}`;

function makeItem(file: File): QItem {
  const p = parseMediaFilename(file.name);
  return {
    id: keyFor(file),
    file,
    title: p.title || file.name,
    year: p.year ? String(p.year) : "2025",
    status: "queued",
    uploadPct: 0,
    progress: 0,
    stage: null,
    jobId: null,
    streamUrl: null,
  };
}

const STAGE_LABEL: Record<string, string> = {
  download: "Downloading",
  "360p": "Encoding 360p",
  "720p": "Encoding 720p",
  "1080p": "Encoding 1080p",
  package: "Packaging HLS+DASH",
  subtitles: "Subtitles",
  thumbnail: "Thumbnail",
  upload: "Publishing",
  ready: "Ready",
};

export function UploadQueue({ files, onClear }: UploadQueueProps) {
  const [items, setItems] = useState<QItem[]>([]);
  const [started, setStarted] = useState(false);
  const [genre, setGenre] = useState<Genre>("Action");
  const [rating, setRating] = useState<Rating>("PG-13");
  const [tag, setTag] = useState<Tag>(null);

  const itemsRef = useRef<QItem[]>([]);
  itemsRef.current = items;
  const runningRef = useRef(false);
  const processedRef = useRef<Set<string>>(new Set());

  const update = useCallback((id: string, patch: Partial<QItem>) => {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  }, []);

  // Sequential driver: upload one file at a time (server transcodes one at a
  // time too). processedRef guards against double-starting regardless of render
  // timing; the loop re-reads the latest queue so files added mid-run are picked up.
  const drain = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    try {
      for (;;) {
        const it = itemsRef.current.find(
          (i) => i.status === "queued" && !processedRef.current.has(i.id),
        );
        if (!it) break;
        processedRef.current.add(it.id);

        if (it.file.size > MAX_UPLOAD_MB * 1024 * 1024) {
          update(it.id, { status: "error", error: `Too large (max ${MAX_UPLOAD_MB} MB)` });
          continue;
        }
        update(it.id, { status: "uploading", uploadPct: 0 });
        try {
          const res = await uploadVideo(
            it.file,
            {
              title: it.title,
              genre,
              year: Number.parseInt(it.year, 10) || 2025,
              rating,
              tag: tag ?? undefined,
            },
            (pct) => update(it.id, { uploadPct: pct }),
          );
          update(it.id, { status: "transcoding", jobId: res.job_id, uploadPct: 100 });
        } catch (e) {
          update(it.id, { status: "error", error: (e as Error).message });
        }
      }
    } finally {
      runningRef.current = false;
    }
  }, [genre, rating, tag, update]);

  // Merge newly dropped files into the queue (dedupe by name+size+mtime).
  useEffect(() => {
    setItems((prev) => {
      const have = new Set(prev.map((i) => i.id));
      const additions = files.filter((f) => !have.has(keyFor(f))).map(makeItem);
      return additions.length ? [...prev, ...additions] : prev;
    });
  }, [files]);

  // Once started, keep the driver going as new items arrive.
  useEffect(() => {
    if (started) void drain();
  }, [started, items, drain]);

  // Poll transcode progress for uploaded jobs.
  const activeKey = items
    .filter((i) => i.status === "transcoding")
    .map((i) => i.jobId)
    .join(",");
  useEffect(() => {
    const jobs = itemsRef.current.filter((i) => i.status === "transcoding" && i.jobId);
    if (!jobs.length) return;
    let alive = true;
    const poll = async () => {
      await Promise.all(
        jobs.map(async (it) => {
          try {
            const s = await getJobStatus(it.jobId!);
            if (!alive) return;
            if (s.status === "complete" && s.stream_url) {
              update(it.id, { status: "ready", progress: 100, streamUrl: s.stream_url });
            } else {
              update(it.id, { progress: s.progress, stage: s.stage });
            }
          } catch {
            /* keep polling */
          }
        }),
      );
    };
    void poll();
    const t = setInterval(poll, 2500);
    return () => {
      alive = false;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey]);

  const removeItem = (id: string) => {
    processedRef.current.delete(id);
    setItems((prev) => prev.filter((i) => i.id !== id));
  };
  const reset = () => {
    processedRef.current = new Set();
    setStarted(false);
    setItems([]);
    onClear();
  };

  if (!items.length) return null;

  const counts = items.reduce<Record<string, number>>((a, i) => {
    a[i.status] = (a[i.status] ?? 0) + 1;
    return a;
  }, {});
  const allDone = items.every((i) => i.status === "ready" || i.status === "error");

  const select =
    "rounded-lg border border-white/20 bg-white/5 px-2.5 py-1.5 text-xs text-white outline-none focus:border-white/40";

  return (
    <div className="space-y-4 rounded-2xl bg-white/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-semibold">
          Upload queue{" "}
          <span className="text-xs font-normal text-white/50">
            ({items.length} · {counts.ready ?? 0} ready · {(counts.uploading ?? 0) + (counts.transcoding ?? 0)} processing)
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!started ? (
            <>
              {/* Shared defaults applied to every file in this batch */}
              <select aria-label="Genre" value={genre} onChange={(e) => setGenre(e.target.value as Genre)} className={select}>
                {GENRES.map((g) => (
                  <option key={g} value={g} className="bg-black">{g}</option>
                ))}
              </select>
              <select aria-label="Rating" value={rating} onChange={(e) => setRating(e.target.value as Rating)} className={select}>
                {RATINGS.map((r) => (
                  <option key={r} value={r} className="bg-black">{r}</option>
                ))}
              </select>
              <select aria-label="Tag" value={tag ?? ""} onChange={(e) => setTag((e.target.value || null) as Tag)} className={select}>
                <option value="" className="bg-black">No tag</option>
                {TAGS.map((t) => (
                  <option key={t} value={t} className="bg-black">{t}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setStarted(true)}
                className="rounded-lg bg-white px-4 py-1.5 text-xs font-bold text-black transition-opacity hover:opacity-90"
              >
                Start {items.length} upload{items.length > 1 ? "s" : ""}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={reset}
              disabled={!allDone}
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Clear queue
            </button>
          )}
        </div>
      </div>

      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-center gap-3">
              <StatusIcon status={it.status} />
              <div className="min-w-0 flex-1">
                {it.status === "queued" && !started ? (
                  <input
                    value={it.title}
                    onChange={(e) => update(it.id, { title: e.target.value })}
                    className="w-full rounded-md border border-white/15 bg-white/5 px-2 py-1 text-sm text-white outline-none focus:border-white/40"
                  />
                ) : (
                  <div className="truncate text-sm font-semibold text-white">{it.title}</div>
                )}
                <div className="truncate text-[11px] text-white/45">
                  {it.file.name} · {(it.file.size / (1024 * 1024)).toFixed(0)} MB
                </div>
              </div>
              <div className="w-32 shrink-0 text-right text-[11px] text-white/60">
                {statusText(it)}
              </div>
              {(it.status === "queued" || it.status === "error") && (
                <button
                  type="button"
                  aria-label="Remove"
                  onClick={() => removeItem(it.id)}
                  className="rounded-md p-1 text-white/40 hover:bg-white/10 hover:text-white/80"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
              {it.status === "ready" && it.streamUrl && (
                <a
                  href={`/player?url=${encodeURIComponent(it.streamUrl)}`}
                  className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-[11px] font-semibold text-white hover:bg-white/20"
                >
                  <Play className="h-3 w-3" /> Play
                </a>
              )}
            </div>

            {(it.status === "uploading" || it.status === "transcoding") && (
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full bg-white transition-all"
                  style={{ width: `${it.status === "uploading" ? it.uploadPct : it.progress}%` }}
                />
              </div>
            )}
            {it.error && <div className="mt-1 text-[11px] text-rose-400">{it.error}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatusIcon({ status }: { status: ItemStatus }) {
  if (status === "ready") return <Check className="h-4 w-4 shrink-0 text-emerald-400" />;
  if (status === "error") return <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />;
  if (status === "uploading" || status === "transcoding")
    return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-white/70" />;
  return <span className="h-2 w-2 shrink-0 rounded-full bg-white/30" />;
}

function statusText(it: QItem): string {
  switch (it.status) {
    case "queued":
      return "Queued";
    case "uploading":
      return `Uploading ${it.uploadPct}%`;
    case "transcoding":
      // stage is null / "queued" until the worker actually picks it up.
      if (!it.stage || it.stage === "queued") return "Waiting for worker…";
      return `${STAGE_LABEL[it.stage] ?? "Transcoding"} ${it.progress}%`;
    case "ready":
      return "Ready ✓";
    case "error":
      return "Failed";
  }
}
