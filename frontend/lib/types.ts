export type Genre = "Action" | "Sci-Fi" | "Drama" | "Comedy" | "Documentary";

export type Rating = "G" | "PG" | "PG-13" | "R" | "NC-17";

export type Tag =
  | "Trending"
  | "New Release"
  | "Award Winner"
  | "Editor's Pick"
  | "Popular"
  | null;

export type MovieStatus = "processing" | "ready";

export type Movie = {
  id: string;
  title: string;
  genre: string;
  year: number;
  rating: string;
  duration: string;
  description: string;
  tag: Tag;
  /** CSS background-image value used for the card / hero artwork. */
  gradient: string;
  status?: MovieStatus;
  /** HLS master playlist URL (playable once status === "ready"). */
  manifestUrl?: string | null;
  /** DASH manifest URL for the same CMAF segments. */
  dashUrl?: string | null;
  /** Poster frame extracted from the source video. */
  thumbnailUrl?: string | null;
  /** Transcode progress 0-100. */
  progress?: number;
};
