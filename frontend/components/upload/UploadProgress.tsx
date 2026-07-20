"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { getJobStatus } from "../../lib/api";

type UploadProgressProps = {
  /** Real upload progress 0-100 (from XHR) before the job id exists. */
  uploadPct: number;
  jobId: string | null;
  onComplete: (streamUrl: string) => void;
};

type StepState = "done" | "active" | "pending";

const STEPS = [
  { key: "upload", label: "Upload" },
  { key: "download", label: "Download" },
  { key: "360p", label: "360p" },
  { key: "720p", label: "720p" },
  { key: "1080p", label: "1080p" },
  { key: "hls", label: "HLS" },
  { key: "dash", label: "DASH" },
  { key: "thumbnail", label: "Thumbnail" },
  { key: "publish", label: "Publish" },
] as const;

// Worker stage -> index of the active step in STEPS.
const STAGE_TO_INDEX: Record<string, number> = {
  download: 1,
  "360p": 2,
  "720p": 3,
  "1080p": 4,
  package: 5, // HLS + DASH
  thumbnail: 7,
  upload: 8,
};

const STAGE_LABEL: Record<string, string> = {
  download: "Downloading source",
  "360p": "Encoding 360p rendition",
  "720p": "Encoding 720p rendition",
  "1080p": "Encoding 1080p rendition",
  package: "Packaging HLS + DASH",
  thumbnail: "Extracting thumbnail",
  upload: "Publishing segments",
};

export function UploadProgress({ uploadPct, jobId, onComplete }: UploadProgressProps) {
  const [pct, setPct] = useState(0);
  const [stage, setStage] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!jobId) {
      setPct(0);
      setStage(null);
      setDone(false);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const s = await getJobStatus(jobId);
        if (!active) return;
        setPct(s.progress);
        setStage(s.stage);
        if (s.status === "complete" && s.stream_url) {
          setPct(100);
          setDone(true);
          onCompleteRef.current(s.stream_url);
          return;
        }
      } catch {
        /* keep polling */
      }
      timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  if (!jobId && uploadPct === 0) {
    return (
      <div className="text-xs text-white/50">
        Fill out the form and submit to start an upload.
      </div>
    );
  }

  // Per-step states + the current summary.
  const states: StepState[] = STEPS.map((_, i) => {
    if (done) return "done";
    if (!jobId) return i === 0 ? "active" : "pending";
    const active = STAGE_TO_INDEX[stage ?? ""] ?? 1;
    if (stage === "package") {
      if (i < 5) return "done";
      return i === 5 || i === 6 ? "active" : "pending";
    }
    if (i < active) return "done";
    if (i === active) return "active";
    return "pending";
  });

  const summary = done
    ? "Ready ✓"
    : !jobId
      ? uploadPct >= 100
        ? "Finishing upload…"
        : "Uploading…"
      : (STAGE_LABEL[stage ?? ""] ?? "Transcoding…");
  const barPct = !jobId ? uploadPct : pct;

  return (
    <div className="space-y-3">
      {/* Checklist stepper */}
      <div className="flex flex-wrap items-center gap-1.5">
        {STEPS.map((step, i) => {
          const st = states[i];
          return (
            <div key={step.key} className="group relative">
              <div
                className={[
                  "flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors",
                  st === "done"
                    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                    : st === "active"
                      ? "border-white/40 bg-white/15 text-white"
                      : "border-white/10 bg-white/5 text-white/35",
                ].join(" ")}
              >
                {st === "done" ? (
                  <Check className="h-3 w-3" />
                ) : st === "active" ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
                {step.label}
              </div>
              {/* Hover tooltip: what's happening on this step */}
              <div className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-lg bg-black/90 px-2.5 py-1.5 text-[11px] text-white shadow-xl ring-1 ring-white/10 group-hover:block">
                {st === "done"
                  ? `${step.label} · done`
                  : st === "active"
                    ? `${summary}${jobId && !done ? ` · ${pct}%` : ""}`
                    : `${step.label} · pending`}
              </div>
            </div>
          );
        })}
      </div>

      {/* Overall bar + summary */}
      <div>
        <div className="flex items-center justify-between text-xs text-white/70">
          <span>{summary}</span>
          <span>{barPct}%</span>
        </div>
        <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-full transition-all ${done ? "bg-emerald-400" : "bg-white"}`}
            style={{ width: `${barPct}%` }}
          />
        </div>
      </div>
    </div>
  );
}
