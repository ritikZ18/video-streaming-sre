## Database Design & Usage

This document explains how the **catalog database** is used in the mini video streaming platform, along with schema, typical queries, and how the UI interacts with it.

The focus here is the **movie catalog** (metadata), not the raw video storage (which lives in object storage like S3).

---

## 1. Role of the Database

The database is used to store:

- **Movie metadata**: title, description, genre, year, rating, duration, and tags.
- **Playback information**: URL of the HLS master manifest and optional thumbnail artwork.
- **Operational metadata**: creation/update timestamps, flags like `is_featured`.

The database is **not** used for:

- Storing raw video files or HLS segments (that belongs in S3).
- Long‑term logging or metrics (those are in Prometheus / log storage).

Relational DB (e.g. Postgres) is preferred because:

- Catalog data is structured and benefits from **joins and constraints**.
- It’s familiar to interviewers and easy to reason about.

---

## 2. Schema (Catalog)

Example Postgres schema:

```sql
CREATE TABLE movies (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title          TEXT NOT NULL,
  description    TEXT,
  genre          TEXT NOT NULL,
  year           INT  NOT NULL,
  rating         TEXT NOT NULL,               -- e.g. G, PG, PG-13, R
  duration       TEXT,                         -- human readable: "2h 10m"
  tag            TEXT,                         -- e.g. 'Trending', 'New Release'

  manifest_url   TEXT NOT NULL,               -- HLS master.m3u8
  thumbnail_url  TEXT,                        -- Optional artwork

  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_movies_genre ON movies (genre);
CREATE INDEX idx_movies_tag   ON movies (tag);
CREATE INDEX idx_movies_year  ON movies (year);
```

You can extend this with:

- `is_featured` (for hero selection).
- `popularity_score` (for sorting “trending”).
- `language`, `audio_tracks`, `subtitles`, etc.

---

## 3. How the UI Uses the Database

The **Apple TV–style UI** doesn’t talk to the DB directly; it uses a **Catalog API** that queries the database.

Typical queries:

- **Home page / hero**:
  - “Give me the most recent or featured movies with a `tag` like `Trending`.”
- **Genre rows**:
  - “List movies where `genre = 'Action'` sorted by `created_at DESC`.”
- **Search**:
  - “Find movies where `title ILIKE '%query%' OR genre ILIKE '%query%'`.”

Example pseudo‑queries:

```sql
-- Trending carousel
SELECT * FROM movies
WHERE tag IN ('Trending', 'New Release')
ORDER BY created_at DESC
LIMIT 20;

-- Genre carousel
SELECT * FROM movies
WHERE genre = 'Sci-Fi'
ORDER BY created_at DESC
LIMIT 20;

-- Search
SELECT * FROM movies
WHERE title ILIKE '%' || :q || '%'
   OR genre ILIKE '%' || :q || '%'
ORDER BY created_at DESC
LIMIT 50;
```

The **Add Movie** flow in the UI calls a `POST /catalog/movies` endpoint that:

1. Validates the request.
2. Inserts a new row into `movies`.
3. Returns the created record back to the UI so it can be added to state.

---

## 4. Write Paths

There are two main ways rows are written to the database:

### 4.1 Via Upload + Transcode Pipeline

- Upload API enqueues a job.
- Transcode worker finishes HLS packaging and then:
  - Either **creates** a new row in `movies`.
  - Or **updates** an existing row with `manifest_url` and technical fields.

This path ensures catalog entries always match actual HLS assets.

### 4.2 Via Admin Catalog API (UI Add Movie)

- The UI’s **Add Movie Panel** collects:
  - `title`, `genre`, `year`, `rating`, `duration`, `description`, `tag`.
  - `manifest_url` (optional in v1 – can be derived from movie ID later).
- Sends request to `POST /catalog/movies`.
- Catalog service inserts a row and returns it to the UI.

This path is useful when:

- You already have HLS content (demo assets) and just need metadata.
- You are developing the UI and don’t want to run the full transcode pipeline.

---

## 5. Operational Considerations

### 5.1 Migrations

- Use standard migration tooling (e.g. Alembic for SQLAlchemy, or Django migrations).
- For a portfolio project, keep migrations simple and documented:
  - `docs/database.md` can mention the migration strategy.

### 5.2 Backups

- In a real environment:
  - Use managed Postgres (e.g. RDS) with automated snapshots.
  - Set retention and PITR (point‑in‑time recovery) where possible.
- In this project:
  - Mention backups in documentation to show awareness, even if not fully implemented.

### 5.3 Performance

- Use indexes for common filters (`genre`, `tag`, `year`).
- Keep queries simple and cover 99% of reads with a few access patterns.

---

## 6. How to Talk About This in Interviews

Key talking points:

- **Separation of responsibilities**:
  - DB for structured metadata; object storage for video; Prometheus for metrics.
- **Simple, well‑indexed schema**:
  - Designed for the **queries the UI actually makes**.
- **Safe write paths**:
  - Controlled via APIs (Upload API, Catalog API), not ad‑hoc SQL edits.
- **Evolution path**:
  - Easy to add new fields, track popularity, or support user‑specific lists in future.

This shows that you understand **data modeling for streaming products** and how the **UI + APIs + DB** fit together.

