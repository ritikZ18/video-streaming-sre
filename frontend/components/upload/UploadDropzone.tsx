"use client";

import { useCallback, useState } from "react";
import { UploadCloud, Film } from "lucide-react";

type UploadDropzoneProps = {
  /** How many files are currently queued (for the hint text). */
  count?: number;
  onFilesSelected: (files: File[]) => void;
};

export function UploadDropzone({ count = 0, onFilesSelected }: UploadDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      // Keep only video files.
      const picked = Array.from(files).filter(
        (f) => f.type.startsWith("video/") || /\.(mp4|mov|mkv|webm|avi)$/i.test(f.name),
      );
      if (picked.length) onFilesSelected(picked);
    },
    [onFilesSelected],
  );

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        handleFiles(event.dataTransfer.files);
      }}
      onClick={() => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "video/*";
        input.multiple = true;
        input.onchange = (event) => {
          const target = event.target as HTMLInputElement | null;
          handleFiles(target?.files ?? null);
        };
        input.click();
      }}
      role="button"
      tabIndex={0}
      aria-label="Add video files"
      className={[
        "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors focus-visible:ring-2 focus-visible:ring-white/50",
        dragOver ? "border-sky-400 bg-sky-400/5" : "border-white/20 bg-white/5",
      ].join(" ")}
    >
      {count > 0 ? (
        <div className="flex items-center gap-3">
          <Film className="h-9 w-9 text-white/60" />
          <div className="text-left">
            <div className="text-sm font-semibold">
              {count} video{count > 1 ? "s" : ""} queued
            </div>
            <div className="text-xs text-white/60">Drop or click to add more</div>
          </div>
        </div>
      ) : (
        <>
          <UploadCloud className="mb-3 h-8 w-8 text-white/50" />
          <div className="text-sm font-medium text-white/80">
            Drop videos or click to browse
          </div>
          <div className="mt-1 text-xs text-white/40">
            MP4, MOV, MKV · multiple files supported
          </div>
        </>
      )}
    </div>
  );
}
