"use client";

import { useState, useEffect } from "react";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { UploadDropzone } from "../../components/upload/UploadDropzone";
import { UploadForm } from "../../components/upload/UploadForm";
import { UploadProgress } from "../../components/upload/UploadProgress";
import { AdminMovieForm } from "../../components/upload/AdminMovieForm";
import type { Movie } from "../../lib/types";
import { getJobStatus, uploadVideo } from "../../lib/api";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [movieMeta, setMovieMeta] = useState<Partial<Movie> | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);

  useEffect(() => {
    let timer: NodeJS.Timeout | undefined;
    if (!jobId) {
      return;
    }
    const poll = async () => {
      try {
        const status = await getJobStatus(jobId);
        if (status.status === "complete" && status.stream_url) {
          setStreamUrl(status.stream_url);
          return;
        }
        timer = setTimeout(poll, 3000);
      } catch {
        timer = setTimeout(poll, 5000);
      }
    };
    void poll();
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  return (
    <div className="min-h-screen bg-black text-white">
      <Navbar onAddMovieClick={() => {}} />
      <main className="px-8 pt-24 pb-16">
        <div className="mb-8 max-w-3xl">
          <h1 className="text-2xl font-bold tracking-tight">Upload</h1>
          <p className="mt-2 text-sm text-white/70">
            Ingest a new video into the pipeline. The Upload API will store the
            raw file, enqueue a transcode job, and the worker will publish HLS
            renditions.
          </p>
        </div>
        <div className="grid gap-8 md:grid-cols-[2fr,3fr]">
          <UploadDropzone file={file} onFileSelected={setFile} />
          <UploadForm
            disabled={!file}
            onSubmitted={async (meta) => {
              setMovieMeta(meta);
              if (!file) return;
              const res = await uploadVideo(file, {
                title: meta.title,
                genre: meta.genre,
                year: meta.year,
                rating: meta.rating,
                duration: meta.duration,
                description: meta.description,
                tag: meta.tag ?? undefined,
              });
              setJobId(res.job_id);
            }}
          />
        </div>
        <div className="mt-10">
          <UploadProgress
            jobId={jobId}
            onComplete={(url) => setStreamUrl(url)}
          />
          {streamUrl && (
            <div className="mt-4 text-sm text-white/80">
              Stream ready: <code className="text-xs">{streamUrl}</code>
            </div>
          )}
        </div>
        <AdminMovieForm />
      </main>
      <Footer />
    </div>
  );
}

