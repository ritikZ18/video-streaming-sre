// Best-effort metadata extraction from a release-style filename, e.g.
//   "Tg @StreamersHub Silo.S03E01.1080p.10bit.WEBRip.6CH.x265.HE.mkv"
//     -> { title: "Silo S03E01", quality: "1080p", codec: "x265" }
// The worker's ffprobe remains the authoritative source once transcoded; this
// is purely to pre-fill the upload form so the admin doesn't retype it.

export type ParsedName = {
  title: string;
  year?: number;
  quality?: string;
  codec?: string;
};

// Tokens that are release noise, never part of a title.
const JUNK =
  /\b(2160p|1080p|720p|480p|4k|uhd|hdr10\+?|hdr|dolby|vision|dv|10bit|8bit|x264|x265|h ?264|h ?265|hevc|avc|av1|web-?rip|web-?dl|blu-?ray|br-?rip|bd-?rip|dvd-?rip|hd-?rip|cam-?rip|remux|proper|repack|extended|uncut|imax|aac|ac3|eac3|ddp?\s?5\s?1|dd\+?|dts(?:-hd)?|truehd|atmos|opus|flac|\d\s?ch|multi|dual|audio|subs?|esub|msub|hc|hdcam|amzn|nf|dsnp|hmax)\b/gi;

const QUALITY = /\b(2160p|1080p|720p|480p|4k)\b/i;
const CODEC = /\b(x265|x264|hevc|h ?265|h ?264|av1)\b/i;
const YEAR = /\b(19\d{2}|20\d{2})\b/;
const SEASON_EP = /\bS(\d{1,2})\s*[.\s]?\s*E(\d{1,2})\b/i;

function titleCase(s: string): string {
  return s
    .split(/\s+/)
    .map((w) => (w.length > 2 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export function parseMediaFilename(filename: string): ParsedName {
  let name = filename.replace(/\.[a-z0-9]{2,4}$/i, ""); // drop extension
  // Strip leading scene/site prefixes: "www.site.com - ", "Tg @Channel ", "[Group] ".
  name = name.replace(/^\s*(?:www\.\S+\s*-\s*|tg\s*@\S+\s+|\[[^\]]*\]\s*|@\S+\s+)/i, "");
  name = name.replace(/[._]+/g, " ").trim(); // dots/underscores -> spaces

  const quality = name.match(QUALITY)?.[1]?.toLowerCase();
  const codec = name.match(CODEC)?.[1]?.toLowerCase().replace(/\s+/g, "");
  const yearMatch = name.match(YEAR);
  const year = yearMatch ? Number(yearMatch[1]) : undefined;
  const se = name.match(SEASON_EP);

  // The title is everything before the first "marker" (year / quality / SxxExx).
  const markers = [yearMatch?.index, name.match(QUALITY)?.index, se?.index].filter(
    (i): i is number => typeof i === "number",
  );
  const cut = markers.length ? Math.min(...markers) : name.length;

  let title = name
    .slice(0, cut)
    .replace(JUNK, " ")
    .replace(/[-–—]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  title = titleCase(title);

  if (se) {
    const s = se[1].padStart(2, "0");
    const e = se[2].padStart(2, "0");
    title = `${title} S${s}E${e}`.trim();
  }

  return { title: title || filename, year, quality, codec };
}
