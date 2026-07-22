"use client";

import { useEffect, useState } from "react";
import type { Movie, Genre, Rating, Tag } from "../../lib/types";
import { parseMediaFilename } from "../../lib/mediaName";

type UploadFormProps = {
  disabled: boolean;
  file: File | null;
  onSubmitted: (meta: Partial<Movie>) => void;
};

const GENRES: Genre[] = ["Action", "Sci-Fi", "Drama", "Comedy", "Documentary"];
const RATINGS: Rating[] = ["G", "PG", "PG-13", "R", "NC-17"];
const TAGS: Exclude<Tag, null>[] = [
  "Trending",
  "New Release",
  "Award Winner",
  "Editor's Pick",
  "Popular",
];

function formatDuration(totalSeconds: number): string {
  const s = Math.round(totalSeconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

export function UploadForm({ disabled, file, onSubmitted }: UploadFormProps) {
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState<Genre>("Action");
  const [year, setYear] = useState("2025");
  const [rating, setRating] = useState<Rating>("PG-13");
  const [duration, setDuration] = useState("");
  const [tag, setTag] = useState<Tag>(null);
  const [description, setDescription] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [detected, setDetected] = useState<string | null>(null);

  // Auto-fill title + year parsed from the release filename. Works for every
  // container (incl. mkv, which the browser can't decode for duration).
  useEffect(() => {
    if (!file) return;
    const p = parseMediaFilename(file.name);
    if (p.title) setTitle(p.title);
    if (p.year) setYear(String(p.year));
    const bits = [p.quality, p.codec].filter(Boolean);
    setDetected(bits.length ? `Detected: ${bits.join(" · ")}` : null);
  }, [file]);

  // Auto-fill duration from the file's metadata. Best-effort: browsers can read
  // mp4/mov/webm (not mkv); the worker sets the authoritative duration via
  // ffprobe when transcoding regardless.
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      if (Number.isFinite(video.duration) && video.duration > 0) {
        setDuration(formatDuration(video.duration));
      }
    };
    video.onerror = () => URL.revokeObjectURL(url);
    video.src = url;
  }, [file]);

  const canSubmit = !disabled && !!title.trim() && !submitting;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);

    const meta: Partial<Movie> = {
      title,
      genre,
      year: Number.parseInt(year, 10) || 2025,
      rating,
      duration,
      description,
      tag,
    };
    onSubmitted(meta);
    setSubmitting(false);
  };

  const sharedInput =
    "w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-xs text-white outline-none placeholder:text-white/30 focus:border-white/40";

  const label =
    "mb-1 block text-[11px] font-semibold uppercase tracking-wide text-white/50";

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-2xl bg-white/5 p-4"
    >
      <div>
        <label className={label}>Title *</label>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Movie title"
          className={sharedInput}
        />
        {detected && (
          <p className="mt-1 text-[10px] text-emerald-300/80">{detected} · auto-filled from filename</p>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className={label}>Genre</label>
          <select
            value={genre}
            onChange={(event) => setGenre(event.target.value as Genre)}
            className={sharedInput}
          >
            {GENRES.map((g) => (
              <option key={g} value={g} className="bg-black">
                {g}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label}>Year</label>
          <input
            value={year}
            onChange={(event) => setYear(event.target.value)}
            className={sharedInput}
          />
        </div>
        <div>
          <label className={label}>Rating</label>
          <select
            value={rating}
            onChange={(event) => setRating(event.target.value as Rating)}
            className={sharedInput}
          >
            {RATINGS.map((r) => (
              <option key={r} value={r} className="bg-black">
                {r}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label}>Duration</label>
          <input
            value={duration}
            onChange={(event) => setDuration(event.target.value)}
            placeholder="e.g. 2h 10m"
            className={sharedInput}
          />
        </div>
        <div>
          <label className={label}>Tag</label>
          <select
            value={tag ?? ""}
            onChange={(event) =>
              setTag((event.target.value || null) as Tag)
            }
            className={sharedInput}
          >
            <option value="" className="bg-black">
              None
            </option>
            {TAGS.map((t) => (
              <option key={t} value={t} className="bg-black">
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className={label}>Description</label>
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Brief synopsis..."
          rows={3}
          className={`${sharedInput} resize-y`}
        />
      </div>
      <button
        type="submit"
        disabled={!canSubmit}
        className={[
          "mt-2 w-full rounded-xl px-4 py-2.5 text-sm font-bold transition-colors",
          canSubmit
            ? "bg-white text-black hover:bg-white/90"
            : "cursor-not-allowed bg-white/10 text-white/40",
        ].join(" ")}
      >
        {submitting ? "Submitting…" : "Submit & Start Transcode"}
      </button>
    </form>
  );
}

