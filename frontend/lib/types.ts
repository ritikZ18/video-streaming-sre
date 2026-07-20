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

export type AudioTrack = { language: string; label: string };
export type SubtitleTrack = {
  language: string;
  label: string;
  url: string;
  forced?: boolean;
};
export type MediaInfo = {
  video?: { codec?: string | null; width?: number | null; height?: number | null } | null;
  audio?: { language: string; label: string }[];
  subtitles?: { language: string; label: string }[];
};

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
  /** Current transcode stage (download, 360p, 720p, 1080p, package, ...). */
  stage?: string | null;
  audioTracks?: AudioTrack[];
  subtitleTracks?: SubtitleTrack[];
  mediaInfo?: MediaInfo | null;
};
