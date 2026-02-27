"use client";

import { useEffect, useState } from "react";

type UploadProgressProps = {
  jobId: string | null;
  onComplete: (streamUrl: string) => void;
};

type Status = "idle" | "uploading" | "queued" | "processing" | "complete";

export function UploadProgress({ jobId, onComplete }: UploadProgressProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!jobId) {
      setStatus("idle");
      setProgress(0);
      return;
    }
    // High-level indicator only; detailed polling happens in page
    setStatus("processing");
    setProgress(60);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    if (status === "processing") {
      setProgress(80);
    }
  }, [jobId, status]);

  if (!jobId) {
    return (
      <div className="text-xs text-white/50">
        Fill out the form and submit to start an upload.
      </div>
    );
  }

  const labelMap: Record<Status, string> = {
    idle: "Waiting…",
    uploading: "Uploading…",
    queued: "Queued…",
    processing: "Transcoding…",
    complete: "Complete ✓",
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-white/70">
        <span>{labelMap[status]}</span>
        <span>{progress}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full bg-white transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

