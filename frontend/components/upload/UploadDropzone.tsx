"use client";

import { useCallback, useState } from "react";
import { UploadCloud, Film } from "lucide-react";

type UploadDropzoneProps = {
  file: File | null;
  onFileSelected: (file: File | null) => void;
};

export function UploadDropzone({ file, onFileSelected }: UploadDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const [selected] = Array.from(files);
      onFileSelected(selected);
    },
    [onFileSelected],
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
        input.onchange = (event) => {
          const target = event.target as HTMLInputElement | null;
          handleFiles(target?.files ?? null);
        };
        input.click();
      }}
      className={[
        "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
        dragOver ? "border-sky-400 bg-sky-400/5" : "border-white/20 bg-white/5",
      ].join(" ")}
    >
      {file ? (
        <div className="flex items-center gap-3">
          <Film className="h-10 w-10 text-white/60" />
          <div className="text-left">
            <div className="text-sm font-semibold">{file.name}</div>
            <div className="text-xs text-white/60">
              {(file.size / (1024 * 1024)).toFixed(1)} MB · Ready to upload
            </div>
          </div>
        </div>
      ) : (
        <>
          <UploadCloud className="mb-3 h-8 w-8 text-white/50" />
          <div className="text-sm font-medium text-white/80">
            Drop video file or click to browse
          </div>
          <div className="mt-1 text-xs text-white/40">
            MP4, MOV, MKV up to 500MB
          </div>
        </>
      )}
    </div>
  );
}

