# StreamSRE — Frontend Architecture & Interaction Reference

> A detailed map of the web frontend: its design system, state management, data flow,
> routing, every component and interaction, the video player internals, and the full
> animation catalogue — plus a prioritised list of improvement opportunities.
>
> Audience: anyone about to **change or improve the UI**. Read §1–§5 for the mental
> model, then jump to the component or the player section you're touching.

---

## 0. TL;DR

- **Yes, it is a TypeScript project** end-to-end (`.ts`/`.tsx`, `tsconfig.json`, `next-env.d.ts`). Strict mode is **off** (`tsconfig.json` `"strict": false`).
- **Stack:** Next.js 14 (App Router) · React 18 · TypeScript 5.5 · Tailwind CSS 3.4 · framer-motion 11 · hls.js 1.5 · lucide-react (icons) · Vitest (tests).
- **No state-management library.** `@tanstack/react-query` is in `package.json` but **unused**. State = plain React hooks + prop drilling; persistence = `sessionStorage` (auth) and `localStorage` (active upload job).
- **No global data cache.** Data comes from `fetch` calls in `lib/api.ts` with `cache: "no-store"`, refreshed by **polling loops** (5 s catalog, 2 s job status, 15 s health, 250 ms player element-sync).
- **Animation** = framer-motion for entrances/transitions + Tailwind CSS transitions for hover/state + one custom keyframe (`slideUp`). Heavy **glassmorphism** motif.
- **Dead/half-wired code to know about:** `StatsOverlay.tsx` is never imported; the Navbar `SearchBar` doesn't actually search.

---

## 1. Tech stack & tooling

| Concern | Choice | Notes |
|---|---|---|
| Framework | **Next.js 14.2** (App Router) | `app/` dir, RSC-capable but almost every page is `"use client"` |
| UI runtime | **React 18.3** | Hooks only, no class components |
| Language | **TypeScript 5.5** | `strict: false`, `noEmit`, `moduleResolution: node`, `jsx: preserve` |
| Styling | **Tailwind 3.4** + PostCSS + autoprefixer | Config: `tailwind.config.mjs`; global CSS: `index.css` |
| Animation | **framer-motion 11** | `motion`, `AnimatePresence` |
| Video | **hls.js 1.5** | Adaptive HLS; native HLS fallback on Safari |
| Icons | **lucide-react** | Tree-shaken SVG icons |
| Telemetry | `navigator.sendBeacon` | QoE events to the beacon-collector service |
| Tests | **Vitest** + Testing Library + jsdom | `frontend/tests/` (one component test present) |
| Lint/format | ESLint (`eslint-config-next`) + Prettier | `eslint.config.mjs`, `.prettierrc` |

`next.config.mjs` maps `NEXT_PUBLIC_*` env vars from `VITE_*` fallbacks and hard-codes local service URLs (`:8000` API, `:8080` origin, `:8001` beacon, `:3000` Grafana, `:9090` Prometheus).

---

## 2. Directory structure

```
frontend/
├─ app/                       # App Router routes (all "use client" except noted)
│  ├─ layout.tsx              # root layout (server) — <html class="dark">, imports index.css
│  ├─ page.tsx                # "/"        Home (hero + genre rows + modal)
│  ├─ browse/page.tsx         # "/browse"  grid + genre filter + search
│  ├─ upload/page.tsx         # "/upload"  (server) redirect("/admin")
│  ├─ admin/page.tsx          # "/admin"   auth gate → upload panel
│  ├─ sre/page.tsx            # "/sre"     service-health dashboard
│  └─ player/page.tsx         # "/player"  reads query params → <VideoPlayer/>
├─ components/
│  ├─ layout/     Navbar.tsx, Footer.tsx
│  ├─ common/     SearchBar.tsx            # decorative only
│  ├─ movie/      HeroCarousel.tsx, ScrollRow.tsx, MovieCard.tsx, MovieDetail.tsx
│  ├─ upload/     UploadDropzone.tsx, UploadForm.tsx, UploadProgress.tsx, AdminMovieForm.tsx
│  └─ player/     VideoPlayer.tsx, StatsOverlay.tsx  # StatsOverlay = dead code
├─ data/movies.ts             # 6 seed movies (public HLS test streams) + genre coverage
├─ lib/
│  ├─ api.ts                  # THE data layer (fetch + XHR + beacons + mapping)
│  ├─ types.ts                # Movie + supporting types
│  ├─ auth.ts                 # sessionStorage admin token
│  └─ mediaName.ts            # filename → {title, year, quality, codec}
├─ index.css                  # tailwind directives + a few globals
└─ tailwind.config.mjs        # design tokens (radii, shadow, slideUp keyframe, fonts)
```

---

## 3. Design system

Defined entirely in **`tailwind.config.mjs`** + **`index.css`** — there is no separate design-token file or theme provider.

### 3.1 Tokens (`tailwind.config.mjs`)
- **Dark mode:** `darkMode: "class"`; `layout.tsx` hard-codes `<html className="dark">` — the app is **always dark**, there is no light theme.
- **Font:** `font-sans` = Apple/system stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, …`). No web-font download.
- **Radii:** `rounded-card` = `0.9rem`, `rounded-modal` = `1.25rem`.
- **Shadow:** `shadow-glow-soft` = `0 12px 40px -12px rgba(0,0,0,0.7)` (soft downward glow on cards, hero Play, Navbar admin button).
- **Keyframe/animation:** `slideUp` (opacity 0→1, `translateY(16px)`→0) exposed as `animate-slideUp` with easing `cubic-bezier(0.25,0.46,0.45,0.94)`. That same cubic-bezier is reused inline on `MovieCard`.

### 3.2 Global CSS (`index.css`)
- `@tailwind base/components/utilities`; `box-sizing: border-box` reset.
- **`::-webkit-scrollbar { display: none }`** — scrollbars are hidden app-wide (that's why `ScrollRow`'s horizontal scroller has no bar; it also uses `[scrollbar-width:none]`).
- Black body background; muted placeholder colour.

### 3.3 Colour & surface language (conventions, not tokens)
Colours are **ad-hoc Tailwind opacity utilities**, applied consistently by convention:
- **Surfaces:** `bg-white/5` (panels/inputs), `bg-white/10`–`/15` (buttons, pills), `bg-black/70`–`/90` (overlays/menus).
- **Text:** `text-white` (primary), `white/70`, `white/60`, `white/40`, `white/30` (decreasing emphasis).
- **Accent:** `indigo-400`/`indigo-500` + `violet-500` (logo gradient, player progress fill, active menu item). Status: `emerald` (done/up), `rose`/`red` (error/down/cancel), `sky-400` (drag-over).
- **Glassmorphism** is the signature motif: `backdrop-blur-xl`/`backdrop-blur-2xl` + `backdrop-saturate-150` on the Navbar, MovieDetail, hero buttons, card play badge, and every player menu.

> **Improvement note:** these colours/opacities are duplicated as string literals across ~15 files. Extracting them into Tailwind theme tokens (e.g. `surface`, `surface-hover`, `accent`) or CSS variables would make a restyle a one-file change.

---

## 4. State-management model

There is **no store and no context** — `layout.tsx` renders `{children}` with zero providers.

```
Page component  (owns useState: movies[], selectedMovie, file, jobId, …)
   │  props: data + callbacks (onClick / onPlay / onMoreInfo / onSubmitted / onComplete)
   ▼
Presentational components (HeroCarousel, ScrollRow → MovieCard, MovieDetail, Upload*)
   │  events bubble up via the callbacks (setSelectedMovie, playMovie, setFile, …)
   ▼
lib/api.ts  (fetch/XHR)  ──►  backend services
```

**Rules of the codebase:**
- Each **page** owns its state with `useState`/`useMemo`/`useRef`; children are pure and receive props + callbacks (classic prop drilling).
- **Cross-session persistence uses Web Storage directly:**
  - `sessionStorage["streamsre-admin"]` = `btoa(user:pass)` — the admin token (`lib/auth.ts`).
  - `localStorage["streamsre.activeJob"]` = job id — so an admin refresh **reattaches** to an in-flight transcode (`app/admin/page.tsx`).
- No optimistic updates, no client cache invalidation — freshness comes from **polling**.

---

## 5. Data layer (`lib/`)

### 5.1 `lib/types.ts` — the `Movie` shape
Central client type: `id, title, genre, year, rating, duration, description, tag, gradient` + optional `status ("processing"|"ready"), manifestUrl, dashUrl, thumbnailUrl, progress, stage, audioTracks[], subtitleTracks[], mediaInfo`. Supporting unions: `Genre`, `Rating`, `Tag` (incl. `null`), plus `AudioTrack`, `SubtitleTrack`, `MediaInfo`.

### 5.2 `lib/api.ts` — everything network
| Function | Method | Purpose |
|---|---|---|
| `listMovies()` | `GET /api/v1/movies/` `no-store` | catalog list → `Movie[]` (polled) |
| `getMovie(id)` | `GET /api/v1/movies/{id}` `no-store` | authoritative metadata + subtitle tracks (player only) |
| `uploadVideo(file, meta, onProgress)` | **XHR** `POST /api/v1/upload` | upload — uses `XMLHttpRequest` so `xhr.upload.onprogress` gives a real % |
| `getJobStatus(jobId)` | `GET /api/v1/jobs/{id}` `no-store` | transcode progress/stage/stream_url |
| `cancelJob(jobId)` | `POST /api/v1/jobs/{id}/cancel` | admin-auth; distinguishes 401/409/404 |
| `createMovie(payload)` | `POST /api/v1/movies/` | admin-auth; register metadata (existing HLS) |
| `adminLogin(user,pass)` | `GET /api/v1/admin/check` | verify creds, then store token |
| `sendBeacon(batch)` | `navigator.sendBeacon` (+`fetch` keepalive) | fire-and-forget QoE telemetry |

Two important helpers:
- **`mapMovie(ApiMovie)`** converts the backend **snake_case** wire shape → the camelCase `Movie`, and synthesises a deterministic **`gradient`** via `gradientFor(id+title)` — a small string hash → one of 8 fixed `linear-gradient`s. This is why uploads with no artwork still get stable, distinct colours.
- **QoE beacons** (`sendBeacon`): `BeaconEvent` = `startup | rebuffer | bitrate_switch | error | heartbeat`, batched and flushed by the player.

### 5.3 `lib/auth.ts`
Client-side admin session in `sessionStorage`. Provides `setAdminToken / getAdminToken / clearAdminToken / isAuthed / authHeader`. **Real enforcement is server-side** (upload-api uses HTTP Basic on write endpoints); this only decides which header to attach and whether to show the admin panel.

### 5.4 `lib/mediaName.ts`
Pure util `parseMediaFilename(name) → {title, year?, quality?, codec?}`. Strips extension + scene prefixes (`www.`, `Tg @…`, `[Group]`), removes release-junk tokens (codecs, `WEBRip`, `10bit`, channel counts…), extracts `1080p/720p/…`, `x264/x265`, a 4-digit year, and `SxxExx`, then title-cases the leading segment. Used by `UploadForm` to pre-fill the title/year and show a "Detected: …" badge.

### 5.5 `data/movies.ts`
`initialMovies: Movie[]` — 6 hard-coded seed titles pointing at **real public CORS-enabled HLS test streams** (mux/apple bipbop). They provide genre coverage + `tag`s so the hero and Trending row are never empty, and they're **merged behind** real uploads (real ids win; clashing seeds are dropped).

---

## 6. Routing & navigation

Six App Router routes: `/`, `/browse`, `/upload` (→ redirect), `/admin`, `/sre`, `/player`.

**Navigation is deliberately mixed:**
- **Nav links** (Navbar) use `next/navigation` `router.push()` with `usePathname()` for active state — the *only* place `router.push` is used.
- **"Play a movie"** uses a **full-page** `window.location.href = "/player?url=…&title=…&id=…&poster=…"` (home `page.tsx`, browse `browse/page.tsx`). The player reads them via `window.location.search` (not `useSearchParams`).
- **Back** on the player = `window.history.back()`.
- `/upload` is a server component that just `redirect("/admin")` (uploading is admin-gated).

> **Improvement note:** the `window.location.href` play-navigation causes a full document reload (loses SPA state, re-fetches). Switching to `router.push` + `useSearchParams`, and passing only `id` (letting the player fetch the rest via `getMovie`), would be faster and cleaner.

---

## 7. Pages — behaviour & data flow

### 7.1 `/` Home (`app/page.tsx`)
- **State:** `movies` (init seeds), `selectedMovie` (drives modal).
- **Effect `[]`:** `load()` = `listMovies()` → merge `[...real, ...seedsNotAlreadyPresent]`; call once + **`setInterval(load, 5000)`** so `processing → ready` flips live; `active` flag guards against setState-after-unmount.
- **Derived:** `grouped` (`useMemo[movies]`) — "Trending" = `tag` Trending/New Release; other buckets by `genre`.
- **Interactions:** card click → `setSelectedMovie` (opens modal); hero **Play** → `playMovie` (full nav to `/player`); hero **More Info** → modal.
- **Renders:** Navbar → HeroCarousel → "Trending Now" ScrollRow (large cards) → one ScrollRow per genre → Footer → conditional MovieDetail.

### 7.2 `/browse` (`app/browse/page.tsx`)
- Same **5 s polling** merge as home.
- **State:** `movies`, `search`, `genre` (`"All"` + 5).
- **Derived:** `filtered` (`useMemo[movies,genre,search]`) — genre match **AND** title/genre `includes` (client-side, **live on every keystroke, no debounce**).
- **Interactions:** genre pills `setGenre`; search `<input>` `setSearch`; **card click jumps straight to the player** (no modal, unlike home).
- **Layout:** responsive auto-fill grid (`minmax(220px,1fr)`).

### 7.3 `/admin` (`app/admin/page.tsx`) — the upload console
Three nested components:
- **`AdminPage`:** `authed`/`checked` (checked prevents an auth flash); on mount `authed = isAuthed()`. Renders `LoginForm` or `AdminPanel`.
- **`LoginForm`:** `username/password/error/busy`; `adminLogin()` → `onSuccess()` or error.
- **`AdminPanel`:**
  - Effect `[]` restores `jobId` from `localStorage` (refresh-safe reattach) and sets `uploadPct=100`.
  - `UploadDropzone` sets `file` → `UploadForm.onSubmitted(meta)` validates size vs `MAX_UPLOAD_MB`, calls `uploadVideo(file, meta, setUploadPct)`, stores `job_id` in state + `localStorage`.
  - `UploadProgress` polls the job; `onComplete(url)` shows a "open player" link + clears `localStorage`; `onCancel` = `clearJob`.
  - Below: `AdminMovieForm` (register existing HLS).
  - _Quirk:_ the metadata is stored write-only (`const [, setMovieMeta]`) — the value is discarded (the form passes meta straight into `uploadVideo`).

### 7.4 `/sre` (`app/sre/page.tsx`)
- **State:** `statuses` (3 services `up|down|unknown`).
- **Effect `[]`:** `check()` = `Promise.all` fetch each service `/health`; runs once + **`setInterval(check, 15000)`**. Status dot: emerald/red/zinc.
- "Open Grafana" → `NEXT_PUBLIC_GRAFANA_URL` in a new tab.

### 7.5 `/player` (`app/player/page.tsx`)
- Thin wrapper. Effect `[]` parses `window.location.search` into `{url,title,poster,id}`; if `id`, calls `getMovie(id)` to override `subs` + authoritative `manifestUrl/title/thumbnailUrl`. Mounts `<VideoPlayer>`. Back = `window.history.back()`.
- _Consequence:_ **real catalog movies get subtitle tracks** (via `id` → `getMovie`); seed streams opened without an `id` rely purely on query params (no captions/audio menus).

---

## 8. Components — interactions & animations

### `movie/HeroCarousel.tsx`
Auto-advancing 520px hero. `index` state + **6 s `setInterval` auto-advance**. framer-motion `AnimatePresence mode="wait"` around a **keyed** `motion.div` — Ken-Burns crossfade (`opacity` + `scale 1.05→1→1.02`, 0.8 s easeOut). Text block uses the Tailwind **`animate-slideUp`** keyframe. Play button disabled/relabelled by `status`/`manifestUrl`. Dot indicators (`setIndex`), active dot animates width `w-2→w-6` via `transition-all`.

### `movie/ScrollRow.tsx`
Horizontal scroller. `showLeft/showRight` recomputed by `checkScroll()` from `scrollLeft/scrollWidth/clientWidth` (wired to `onScroll` + an effect on `movies.length`). Arrows call `scrollBy({left: ±400, behavior:"smooth"})` (**native** smooth scroll). Right arrow only when `showRight && movies.length > 3`. Scrollbar hidden.

### `movie/MovieCard.tsx`
`hovered` state. **Tailwind-only** animation: base `transition-all duration-300 ease-[cubic-bezier(…)]`; hovered → `z-10 -translate-y-1 scale-[1.06] ring-1 ring-white/25` (lift + zoom + ring), else `scale-100 ring-white/5`. Always-on bottom gradient scrim; `tag` pill; title/genre; **hover reveals a centered glass Play badge**. Background = `thumbnailUrl` else synthesized `gradient`.

### `movie/MovieDetail.tsx`
Modal (parent-controlled via `selectedMovie`). framer-motion: backdrop `AnimatePresence` fade; panel `motion.div` slide-up (`y:24→0`, 0.25 s). Backdrop `onClick=onClose`; panel `stopPropagation`. **Glass panel** `bg-zinc-900/70 backdrop-blur-2xl backdrop-saturate-150 ring-1 ring-white/5`. Metadata pills from `[year, rating, duration, genre]`. The `+` button has **no handler** (decorative).

### `layout/Navbar.tsx`
Fixed, **glass** (`bg-black/40 backdrop-blur-xl backdrop-saturate-150`). Logo + `router.push("/")`; NAV_ITEMS Home/Browse/SRE with active = `pathname===href`; Admin button; embeds `<SearchBar>`. Tailwind `transition-colors` only.

### `common/SearchBar.tsx` ⚠️ decorative
`query`/`focused` local state; **expand-on-focus** (`w-40 → w-56`, `transition-[width,border-color]`) with a clear button. **Does not route or filter anything** — the only working search is browse's own input.

### `layout/Footer.tsx`
Static. Credit line + three non-functional buttons (Prometheus/Grafana/Alerts) with `hover:text-white/80`.

### `upload/UploadDropzone.tsx`
`dragOver` state. `onDragOver/Leave/Drop` (with `preventDefault`) → `onFileSelected(first file)`. Click **programmatically creates a hidden `<input type=file accept=video/*>`** and `.click()`s it. Drag state → `border-sky-400 bg-sky-400/5`. Shows file (name/MB) or prompt. `transition-colors`.

### `upload/UploadForm.tsx`
Controlled metadata form. Two `useEffect[file]`: (1) `parseMediaFilename` → prefill title/year + "Detected" badge; (2) off-DOM `<video preload="metadata">` + object URL → client-side duration (mp4/mov/webm; not mkv). `handleSubmit` builds `Partial<Movie>` meta and calls `onSubmitted` (parent uploads). Tailwind-only styling.

### `upload/UploadProgress.tsx`
9-step **checklist stepper** + overall bar + cancel. `pct/stage/done/canceling/cancelError`; `onCompleteRef` keeps the completion callback fresh without re-subscribing the poll. **Effect `[jobId]`:** recursive `poll()` = `getJobStatus` every **2 s via chained `setTimeout`**, stops on `complete`; errors swallowed. `STEPS`/`STAGE_TO_INDEX`/`STAGE_LABEL` drive per-step `done|active|pending` (special-casing `package` → HLS+DASH both active). `Loader2 animate-spin` on the active step; **CSS `group-hover` tooltips**; bar width via inline `%` `transition-all`. Cancel button (`cancelJob`) shown while `jobId && !done`.

### `upload/AdminMovieForm.tsx`
"Register Existing HLS Movie" — metadata only, no file. `createMovie({..., manifest_url: `${ORIGIN_URL}/hls/${hlsId}/master.m3u8`})`, resets fields + shows a message on success. Tailwind-only.

### `player/StatsOverlay.tsx` 💀 dead code
Toggleable placeholder popover (all "—"). **Never imported** — superseded by the player's own `showStats` overlay. Safe to delete.

---

## 9. The Video Player (`components/player/VideoPlayer.tsx`)

The largest, most stateful component — a full custom HLS player. Props: `{src, poster, title, contentId, subtitleTracks}`.

### 9.1 State & refs
- **Playback state:** `playing, current, duration, buffered, volume, muted, fullscreen, loading, error, showControls, menu(null|quality|audio|captions|speed)`.
- **Track state:** `levels[], currentLevel(-1=auto), audioTracks[], currentAudio, currentCaption(-1=off), rate`.
- **Stats state:** `showStats, bitrateKbps, rebuffers, startupMs`.
- **Refs:** `videoRef, hlsRef, containerRef` + telemetry refs (`sessionRef, eventsRef, loadStartRef, rebufferStartRef, gotFirstRef, hideTimer`).

### 9.2 The 7 effects
1. **`[src, flush, pushEvent]` — HLS setup.** New session id (`crypto.randomUUID`), reset telemetry. Native HLS (`video.src`) on Safari, else `new Hls({enableWorker, backBufferLength:60})` + `loadSource/attachMedia`. Subscribes to: `MANIFEST_PARSED` (levels), `LEVEL_LOADED` (**authoritative VOD duration from `details.totalduration`** — the fix for the dead seek bar), `AUDIO_TRACKS_UPDATED`, `AUDIO_TRACK_SWITCHED`, `LEVEL_SWITCHED` (bitrate + `bitrate_switch` beacon), `ERROR` (fatal → error beacon + message). Cleanup `flush()` + `hls.destroy()`.
2. **`[pushEvent]` — native `<video>` listeners** (play/pause/timeupdate/loadedmetadata/durationchange/canplay/waiting/playing/volumechange). `onTime` also re-syncs `playing = !paused` and clears loading; `onWaiting` raises the spinner + marks rebuffer start; `onPlaying` computes **startup_ms** (first) or **rebuffer_ms** (subsequent) and beacons them.
3. **`[src]` — 250 ms element poll.** The bulletproof source-of-truth: every 250 ms copies `!paused/!ended`, `currentTime`, `duration`, `buffered` into React state so the UI can never desync from the media element (this is what stops the ▶ overlay sticking during playback).
4. **`[playing, bitrateKbps, flush, pushEvent]` — 15 s heartbeat.** Pushes a `heartbeat` beacon while playing, then flushes the batch.
5. **`[]` — fullscreen** — `fullscreenchange` → `setFullscreen`.
6. **`[togglePlay, seek, toggleFullscreen, toggleMute]` — keyboard shortcuts** (window): `space`/`k` play, `←`/`j` −10s, `→`/`l` +10s, `↑`/`↓` volume ±0.1, `f` fullscreen, `m` mute.

> There are effectively **three overlapping play/time sync mechanisms** — discrete `<video>` events, the `timeupdate` re-sync, and the 250 ms poll. The poll is the safety net that guarantees correctness even when hls.js drops an event.

### 9.3 Controls & interactions
- Container `onMouseMove={nudge}` shows controls and arms a **2.6 s auto-hide** (only hides while playing & no menu open); `onMouseLeave` hides.
- `<video onClick={togglePlay}>`, `preload="auto"`, `crossOrigin="anonymous"`, `<track>` per subtitle.
- **Seek bar:** a transparent `<input type="range">` overlaid on a 3-layer bar (bg `white/20`, buffered `white/40`, played `indigo-400`, widths via inline `%`).
- **Volume:** range slider (`accent-white`), auto-mutes at 0.
- **Four dropdown menus:** Audio (only if `>1` track), Captions (only if `subtitleTracks`), Quality (Auto + rendition heights, reversed), Speed (0.5–2×). Each mutates hls/video then closes.
- Stats toggle (`Gauge`) shows the live QoE overlay; fullscreen toggle.

### 9.4 Animations
- Shared **`menuAnim`** (`opacity/y:6/scale:0.96`, 0.14 s) spread onto all four menus + the stats overlay, each in `AnimatePresence`.
- Center **Play** button: `AnimatePresence` + `motion.button` pop (`scale:0.8→1`), shown only when paused & not loading & no error.
- Controls bar: `motion.div animate={{opacity: showControls||!playing ? 1 : 0}}` (always mounted, fades).
- Buffering spinner: Lucide `Loader2 animate-spin`, shown **only** when `loading` (genuine buffering/stall).

### 9.5 QoE telemetry pipeline
`pushEvent` appends to `eventsRef`; `flush` ships the batch via `sendBeacon` (session id + `contentId`). Events: `startup` (first frame latency), `rebuffer` (stall duration + count), `bitrate_switch`, `error`, `heartbeat` (15 s). Survives page unload (`sendBeacon`/keepalive).

---

## 10. Animation catalogue (every technique + where)

| Technique | Where | Detail |
|---|---|---|
| framer-motion crossfade (`AnimatePresence`+keyed `motion`) | HeroCarousel | Ken-Burns `opacity`+`scale`, 0.8 s, `mode="wait"` |
| framer-motion fade + slide-up | MovieDetail | backdrop fade + panel `y:24→0`, 0.25 s |
| framer-motion pop / menu pop | VideoPlayer | center-play `scale:0.8`; menus via `menuAnim` 0.14 s |
| framer-motion opacity toggle | VideoPlayer controls bar | `animate={{opacity}}`, always mounted |
| Tailwind keyframe `animate-slideUp` | HeroCarousel text | config `slideUp`, cubic-bezier entrance |
| CSS transitions (dominant) | everywhere | `transition-all/-colors/-opacity/-transform/-[width,…]` on hover/active/disabled |
| CSS transform hover lift | MovieCard | `-translate-y-1 scale-[1.06] ring` |
| Lucide `animate-spin` | UploadProgress, VideoPlayer | active-step + buffering spinners |
| Native smooth scroll | ScrollRow | `scrollBy({behavior:"smooth"})` + arrow reveal |
| Pure CSS hover tooltip | UploadProgress | `group` + `group-hover:block` |
| Glassmorphism | Navbar, MovieDetail, hero, cards, player menus | `backdrop-blur-*` + `backdrop-saturate-150` |

---

## 11. Polling / timing cadence (mental model of "liveness")

| Surface | Interval | Mechanism | Purpose |
|---|---|---|---|
| Home & Browse catalog | **5 s** | `setInterval` | processing→ready flips live |
| Upload job status | **2 s** | chained `setTimeout` | stepper progress |
| SRE health | **15 s** | `setInterval` | service up/down |
| Player element sync | **250 ms** | `setInterval` | UI ↔ media truth |
| Player heartbeat/flush | **15 s** | `setInterval` | QoE telemetry |

---

## 12. Known issues, dead code & gotchas

1. **`StatsOverlay.tsx` is dead** (never imported). Delete it.
2. **Navbar `SearchBar` doesn't search** — local state only. Either wire it (route to `/browse?q=` and read it there) or remove it.
3. **Inconsistent card click behaviour:** home cards open the modal, browse cards jump straight to the player. Pick one interaction model.
4. **Full-page nav for play** (`window.location.href`) reloads the whole app and drops SPA state.
5. **Colour/opacity literals duplicated** across ~15 files — no shared tokens; a restyle touches every file.
6. **`initialMovies` seed streams** always appear in the catalog (even in "prod") — fine for a portfolio, surprising otherwise.
7. **`strict: false`** in `tsconfig` — weaker type safety than it looks.
8. **`react-query` installed but unused** — dead dependency (or an opportunity, see below).
9. Admin metadata state is discarded (`const [, setMovieMeta]`).
10. The MovieDetail `+` button is decorative (no handler).

---

## 13. Improvement opportunities (for the UI enhancement pass)

Ordered by impact-to-effort for *"make it feel more premium / modern"*:

1. **Design tokens.** Move the repeated `white/xx`, radii, accent colours, and glass recipe into `tailwind.config.mjs` theme extensions (or CSS variables). Enables a themeable, one-file restyle and a future light mode.
2. **Motion consistency.** Standardise on framer-motion for entrances (cards, rows, modal, hero) with a shared `variants`/`transition` config, instead of the current mix of framer-motion + ad-hoc CSS transitions. Add `layout`/`layoutId` for the card→detail "shared element" expand (Netflix-style).
3. **Unify navigation.** Replace `window.location.href` play-nav with `router.push('/player?id=…')` + `useSearchParams`; pass only `id` and let the player hydrate everything from `getMovie`. Faster, keeps SPA state, gives every movie its audio/caption menus.
4. **Real search.** Make the Navbar `SearchBar` route to `/browse?q=` and have browse read the query — or drop it.
5. **Data layer.** Adopt the already-installed **react-query** for `listMovies`/`getMovie`/`getJobStatus` — replaces the hand-rolled polling loops with caching, dedupe, background refetch, and `isLoading`/`isError` states (fewer bespoke `useEffect`s, less flicker).
6. **Skeleton/loading states.** Cards, hero, and the grid currently pop in; add shimmer skeletons while `listMovies` resolves.
7. **Accessibility polish.** Focus-visible rings, `aria-pressed` on toggle buttons, trap focus in the modal, and honour `prefers-reduced-motion` for the hero auto-advance and framer transitions.
8. **Player chrome.** Buffered-ahead indicator on hover-scrub, thumbnail preview on the seek bar, a proper settings gear grouping quality/speed/audio/captions, and PiP support.
9. **Delete dead code** (`StatsOverlay`), fix the discarded admin meta, wire or remove the `+` button.
10. **Turn on `strict`** and clean up the resulting types incrementally.

---

## 14. How to run / where it lives

- Dev container: `frontend/Dockerfile` (built by the root `docker-compose.yml`), served on **`http://localhost:3001`**.
- Local dev: `cd frontend && npm install && npm run dev`.
- Env: `NEXT_PUBLIC_API_URL` / `_ORIGIN_URL` / `_BEACON_URL` (see `next.config.mjs`; defaults point at the local stack).
- Tests: `npm run test` (Vitest + jsdom).

> **Branch note:** this document describes the frontend as merged from `origin/dev` (the complete, buildable app: `lib/` + `tailwind.config.mjs` + all features). The earlier `frontend-appletv` base was missing `lib/` and the Tailwind config and could not build — it has now been fast-forwarded to match.

---

## 15. Catalog sources & how movie IDs are made

The catalog on screen is a **merge of three sources**, each with a distinct, stable `id` scheme:

| Source | Where the id comes from | id shape | Playable? |
|---|---|---|---|
| **Uploads** (your videos) | `upload-api` generates `job_id = uuid4()` on upload; **the catalog row id IS the job id** (`services/upload-api/app/routes/upload.py`). The transcode-worker later flips that same row to `ready` by job id. | random UUID, e.g. `6c020302-b314-4dc3-8bdb-e6372f00b6e6` | ✅ yes — has a `manifestUrl` on your origin |
| **TMDB** (metadata catalog) | `lib/tmdb.ts` maps a TMDB movie to `id = "tmdb-" + tmdbId` | `tmdb-1368337` | ❌ no — `displayOnly: true`, no `manifestUrl` |
| **Seed** (`data/movies.ts`) | hard-coded (`"1"`…`"6"`), only shown if TMDB is unreachable | small integer strings | ✅ (public HLS test streams) |

So: **the id you see in `/player?id=…` for one of your uploads is the transcode job id / catalog primary key.** One upload → one UUID → one catalog row → one playable title. The merge rule (`app/page.tsx`, `browse`, `library`) always puts **uploads first** so, when ids or titles collide, the playable upload wins over a catalog-only TMDB entry.

TMDB requests never expose the key: the browser calls the **server proxy** `app/api/tmdb/[...path]/route.ts`, which reads `TMDB_API_KEY` from server runtime env (`docker-compose` → `.env`, gitignored) and forwards to `api.themoviedb.org`. The key is not in the client bundle.

## 16. De-duplication — finding it and preventing re-uploads

Two independent layers, both in `lib/catalog.ts` + their call sites.

**The key.** `titleKey(title)` normalizes a title for comparison: lowercase → strip a stray extension → collapse whitespace. Two titles that normalize to the same string are considered the same movie.

**Layer 1 — display de-dup (`dedupeByTitle`).** Home, Browse, and Library run their merged movie list through `dedupeByTitle`, which keeps the **first** occurrence of each `titleKey` and drops the rest. Because callers order the list *uploads-first, newest-first*, the copy that survives is the best one — and the same video can no longer appear under multiple genre rows (the bug where one upload showed under both Sci-Fi and Action).

**Layer 2 — upload prevention (`UploadQueue`).** Before uploading, the queue fetches the existing catalog once and builds `existingRef = titleSet(listMovies())`. In the sequential upload driver, each file is checked:
```
dupKey = titleKey(item.title)
if existingRef.has(dupKey):  → mark "Already in your library — skipped", do NOT upload
else:                          existingRef.add(dupKey); upload it
```
Adding to `existingRef` *before* uploading also collapses duplicates **within the same batch** (dropping the same file twice), and the dropzone already de-dupes identical `File` objects by `name+size+lastModified`. Net effect: **you can't add the same title twice** — not from the catalog, not within one batch.

> Note: de-dup is by **title**, which is deliberately loose (re-encodes/re-cuts with the same name collapse). Existing duplicate *rows* already in the backend are hidden by Layer 1; physically deleting them needs a backend `DELETE /movies/{id}` endpoint (not built yet).

## 17. Adaptive rendition ladder (incl. 4K / 60fps)

Playback quality is only as high as the renditions the worker produced. `services/transcode-worker/app/profiles.py` defines the rungs (360p → 720p → 1080p → 1440p → 2160p) and `ladder_for(source_height)` picks which to encode: **every rung ≤ the source height, never above** (no upscaling), always at least the lowest.

- 4K/60 source → `[360p, 720p, 1080p, 1440p, 2160p]` — so on a fast connection hls.js auto-selects **2160p**.
- 1080p source → stops at 1080p; 720p → stops at 720p.

Frame rate is preserved (no `fps` filter), so 60fps stays 60fps. The whole ladder is encoded in **one GPU decode pass** (`encode_ladder`), which now **retries NVENC once** on a transient init failure before falling back to CPU — addressing the occasional "GPU didn't start".

> **Existing uploads are capped by whatever ladder was live when they were encoded.** A 4K file transcoded before this change only has segments up to 1080p — the higher rungs don't exist, so the player can't select them. Re-transcode (or re-upload) a title to regenerate the 2160p ladder.

**The stats panel's `Auto · 1080p`** reads the on-screen resolution from the `<video>` element's own `videoHeight` (the decoded frame height) — ground truth that stays correct even if hls.js's `LEVEL_SWITCHED` is missed or `currentLevel`/`loadLevel` read `-1`. Bitrate still comes from hls.js (the element can't report it).

## 18. Inspecting the HLS output (segments & playlists)

The worker writes CMAF/fMP4 output to the **`streamsre-hls-segments`** S3 bucket (floci), keyed by `<job_id>/`. The **origin** (Nginx, `:8080`) proxies it at `/hls/<job_id>/…`. Per title you get:

| File | What it is |
|---|---|
| `master.m3u8` | the multivariant playlist — lists the rendition ladder (`RESOLUTION=…`, `BANDWIDTH=…`) |
| `media_0.m3u8` … `media_N.m3u8` | one media playlist per rendition (the `#EXTINF` segment list) |
| `init-stream0.m4s` … | fMP4 init segment per stream (moov/codec header) |
| `chunk-stream0-00001.m4s` … | the actual media segments (`chunk-stream<rendition>-<seq>.m4s`) |
| `manifest.mpd` | the DASH manifest (same segments, DASH packaging) |
| `thumbnail.jpg` | poster frame |

**List every object for a title** (job id = the movie id in `/player?id=…`):
```bash
docker exec streamsre-transcode-worker python -c "
import boto3,os; s3=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL'],
aws_access_key_id='test',aws_secret_access_key='test',region_name='us-east-1')
for o in s3.list_objects_v2(Bucket='streamsre-hls-segments',Prefix='<JOB_ID>/')['Contents']:
    print(o['Size'], o['Key'])"
```

**Read the master playlist** (see the ladder a title actually has):
```bash
curl -s http://localhost:8080/hls/<JOB_ID>/master.m3u8
```

**Play it straight from the origin** — no browser, no frontend:
```bash
ffplay http://localhost:8080/hls/<JOB_ID>/master.m3u8     # or open the URL in VLC
```

**Find the job id / manifest for a title** (scan the DynamoDB catalog):
```bash
docker exec streamsre-transcode-worker python -c "
import boto3,os; db=boto3.client('dynamodb',endpoint_url=os.environ['DYNAMODB_ENDPOINT_URL'],
aws_access_key_id='test',aws_secret_access_key='test',region_name='us-east-1')
for it in db.scan(TableName='streamsre-catalog')['Items']:
    g=lambda k: list(it.get(k,{}).values())[0] if k in it else ''
    print(g('id'), g('status'), g('title'), g('manifest_url'))"
```

> Raw source uploads live in the separate **`streamsre-raw-uploads`** bucket under `<job_id>/<original-filename>`. Objects live in **MinIO** (volume `minio_data`) and the catalog in **dynamodb-local** (volume `dynamo_data`), so both **survive floci restarts** — only the SQS queue is ephemeral. See `docs/infra-floci.md` §0. Browse objects at the MinIO console `http://localhost:9001`.

## 19. Letterboxed sources & the IMAX / fill button

Cinematic trailers usually **bake a ~2.39:1 letterbox into a 16:9 frame** — the black bars are pixels in the video, not player layout (`cropdetect` on our Godzilla trailer reports the picture is only `1920×796` inside a `1920×1080` frame). Because the frame is already 16:9, `object-fit: cover` on a 16:9 screen can't remove those bars.

The **IMAX** button (`VideoPlayer.tsx`) instead enters fullscreen and applies a CSS `transform: scale(1.35)` (`IMAX_ZOOM`) to the video, zooming until the baked bars are pushed past the container's `overflow: hidden` edge. The result fills the screen edge-to-edge, cropping a little off the sides — exactly like VLC's *fill/crop*. It's an explicit opt-in: on a genuinely full-frame 16:9 source it would over-zoom, which is the accepted trade for "no black bars". (A future refinement is to run `cropdetect` at transcode time and store the true content aspect so the zoom can be exact per title.)
