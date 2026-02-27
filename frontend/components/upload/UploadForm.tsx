"use client";

import { useState } from "react";
import type { Movie, Genre, Rating, Tag } from "../../lib/types";

type UploadFormProps = {
  disabled: boolean;
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

export function UploadForm({ disabled, onSubmitted }: UploadFormProps) {
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState<Genre>("Action");
  const [year, setYear] = useState("2025");
  const [rating, setRating] = useState<Rating>("PG-13");
  const [duration, setDuration] = useState("");
  const [tag, setTag] = useState<Tag>(null);
  const [description, setDescription] = useState("");

  const [submitting, setSubmitting] = useState(false);

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

