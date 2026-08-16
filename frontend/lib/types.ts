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
  video?: { codec?: string | null; width?: number | null; height?: number | null; fps?: number | null } | null;
  audio?: {
    language: string;
    label: string;
    codec?: string | null;
    channels?: number | null;
    default?: boolean;
    /** Muxed-in external track for a silent source. */
    external?: boolean;
  }[];
  subtitles?: {
    language: string;
    label: string;
    codec?: string | null;
    forced?: boolean;
    /** Text sub (convertible to WebVTT) vs image-based (PGS/VobSub). */
    text?: boolean;
    /** Whether a playable WebVTT sidecar was produced. */
    extracted?: boolean;
  }[];
};

/** One row of the live audio/subtitle extraction checklist shown while a title is
 *  processing. `image` = an image-based subtitle that can't be shown in-browser. */
export type ExtractTask = {
  kind: "audio" | "subtitle";
  label: string;
  lang?: string;
  codec?: string | null;
  channels?: number | null;
  forced?: boolean;
  state: "pending" | "done" | "image";
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
  /** HLS master playlist URL (playable once status === "ready"). H.264 — universal. */
  manifestUrl?: string | null;
  /** HEVC (HDR) master for HDR titles; used only where the browser can decode HEVC. */
  hdrManifestUrl?: string | null;
  /** DASH manifest URL for the same CMAF segments. */
  dashUrl?: string | null;
  /** Poster frame extracted from the source video (2:3 for cards). */
  thumbnailUrl?: string | null;
  /** Custom poster uploaded by an admin; preferred over thumbnailUrl on cards. */
  posterUrl?: string | null;
  /** Wide 16:9 art for the hero (TMDB backdrop / custom); falls back to thumbnailUrl. */
  backdropUrl?: string | null;
  /** Catalog visibility: published (public), unlisted (link-only), draft (hidden). */
  visibility?: "draft" | "published" | "unlisted";
  /** True for catalog-only titles (e.g. TMDB) that have no playable stream. */
  displayOnly?: boolean;
  /** Transcode progress 0-100. */
  progress?: number;
  /** Current transcode stage (download, 360p, 720p, 1080p, package, ...). */
  stage?: string | null;
  audioTracks?: AudioTrack[];
  subtitleTracks?: SubtitleTrack[];
  mediaInfo?: MediaInfo | null;
  /** True once an admin attached an external audio track to a silent title. */
  hasExternalAudio?: boolean;
  /** Frame interpolation (I/O Framer) lifecycle + request. */
  interpRequested?: boolean;
  interpTargetFps?: number | null;
  interpStatus?: "queued" | "processing" | "done" | "skipped" | "failed" | null;
  interpDetail?: string | null;
  /** WebVTT storyboard (hover-scrub sprite map) served beside the manifest. */
  storyboardUrl?: string | null;
  /** Non-destructive smoothed rendition; when set the player shows a Smooth toggle. */
  interpManifestUrl?: string | null;
  /** Target fps of the smoothed rendition (labels the Smooth toggle). */
  interpFps?: number | null;
  /** Live interpolation progress (I/O Framer 0-100) + stage + epoch it started. */
  interpProgress?: number | null;
  interpStage?: string | null;
  interpStartedAt?: number | null;
  /** Live audio/subtitle extraction checklist (populated while processing). */
  extractTasks?: ExtractTask[];
};

// --- Live streaming ---
export type LiveState =
  | "idle"
  | "scheduled"
  | "starting"
  | "live"
  | "ended"
  | "error";

/** A live channel as a viewer sees it (sanitized — no stream key / ingest URL). */
export type LiveEvent = {
  id: string;
  title: string;
  description?: string | null;
  sourceType: "ingest" | "playout";
  state: LiveState;
  audioOnly: boolean;
  /** Live HLS master ({origin}/live/<id>/master.m3u8); host-rewritten for tunnel. */
  manifestUrl?: string | null;
  scheduledStart?: string | null;
  scheduledEnd?: string | null;
  startedAt?: string | null;
  posterUrl?: string | null;
  backdropUrl?: string | null;
};
