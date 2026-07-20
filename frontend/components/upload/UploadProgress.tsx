"use client";

import { useEffect, useRef, useState } from "react";
import { getJobStatus } from "../../lib/api";

type UploadProgressProps = {
  /** Real upload progress 0-100 (from XHR) before the job id exists. */
  uploadPct: number;
  /** Set once the upload completes and transcoding is queued. */
  jobId: string | null;
  onComplete: (streamUrl: string) => void;
};

export function UploadProgress({ uploadPct, jobId, onComplete }: UploadProgressProps) {
  const [transcodePct, setTranscodePct] = useState(0);
  const [done, setDone] = useState(false);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!jobId) {
      setTranscodePct(0);
      setDone(false);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const s = await getJobStatus(jobId);
        if (!active) return;
        setTranscodePct(s.progress);
        if (s.status === "complete" && s.stream_url) {
          setTranscodePct(100);
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

  let label: string;
  let pct: number;
  if (done) {
    label = "Ready ✓";
    pct = 100;
  } else if (!jobId) {
    label = uploadPct >= 100 ? "Finishing upload…" : "Uploading…";
    pct = uploadPct;
  } else {
    label = "Transcoding…";
    pct = transcodePct;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-white/70">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full transition-all ${done ? "bg-emerald-400" : "bg-white"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
