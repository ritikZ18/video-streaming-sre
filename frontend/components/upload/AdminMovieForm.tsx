"use client";

import { useState } from "react";
import type { Genre, Rating, Tag } from "../../lib/types";
import { createMovie } from "../../lib/api";

const GENRES: Genre[] = ["Action", "Sci-Fi", "Drama", "Comedy", "Documentary"];
const RATINGS: Rating[] = ["G", "PG", "PG-13", "R", "NC-17"];
const TAGS: Exclude<Tag, null>[] = [
  "Trending",
  "New Release",
  "Award Winner",
  "Editor's Pick",
  "Popular",
];

export function AdminMovieForm() {
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState<Genre>("Action");
  const [year, setYear] = useState("2025");
  const [rating, setRating] = useState<Rating>("PG-13");
  const [duration, setDuration] = useState("");
  const [tag, setTag] = useState<Tag>(null);
  const [description, setDescription] = useState("");
  const [hlsId, setHlsId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const canSubmit = !!title.trim() && !!hlsId.trim() && !submitting;

  const sharedInput =
    "w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-xs text-white outline-none placeholder:text-white/30 focus:border-white/40";

  const label =
    "mb-1 block text-[11px] font-semibold uppercase tracking-wide text-white/50";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setMessage(null);
    try {
      const desc = description || "";
      const composedDescription = hlsId
        ? `${desc}\n\nHLS prefix id: ${hlsId}`
        : desc;
      await createMovie({
        title,
        genre,
        year: Number.parseInt(year, 10) || 2025,
        rating,
        duration: duration || undefined,
        description: composedDescription || undefined,
        tag: tag || undefined,
      });
      setMessage("Movie metadata saved. Ensure HLS is under segments bucket using this id.");
      setTitle("");
      setDuration("");
      setDescription("");
      setHlsId("");
      setTag(null);
    } catch (error) {
      setMessage(`Failed to save movie: ${(error as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-12 max-w-3xl rounded-2xl bg-white/5 p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">
        Admin · Register Existing HLS Movie
      </h2>
      <p className="mb-4 text-xs text-white/60">
        Use this when you already have HLS assets in the segments bucket. The{" "}
        <code className="text-[10px]">
          HLS Folder ID
        </code>{" "}
        should match the prefix under{" "}
        <code className="text-[10px]">streamsre-hls-segments/&lt;id&gt;/</code>.
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className={label}>Title *</label>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Movie title"
            className={sharedInput}
          />
        </div>
        <div>
          <label className={label}>HLS Folder ID *</label>
          <input
            value={hlsId}
            onChange={(event) => setHlsId(event.target.value)}
            placeholder="e.g. movie-123 (matches S3 prefix)"
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
          {submitting ? "Saving…" : "Save Metadata Only"}
        </button>
        {message && (
          <p className="mt-2 text-xs text-white/70">
            {message}
          </p>
        )}
      </form>
    </div>
  );
}

