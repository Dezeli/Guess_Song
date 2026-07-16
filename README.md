# Guess Song

Real-time music quiz service built around official playable YouTube sources.

## Stack

- Backend: Django, Django Ninja, Channels, Celery
- Frontend: React, Vite, TypeScript, Zustand
- Data: PostgreSQL, Redis
- Runtime: Docker Compose, Nginx

## Structure

```text
backend/
  apps/
    core/
    catalog/
    ingestion/
    moderation/
    quizzes/
    rooms/
  config/

frontend/
  src/

nginx/
docker-compose.yml
docker-compose.prod.yml
```

## Local Development

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Then open:

- Frontend through Nginx: http://localhost
- Backend health check: http://localhost/api/health
- Django admin: http://localhost/admin

## Backend Apps

- `core`: common base models, utilities, exceptions, health check
- `catalog`: artists, songs, albums, charts, external IDs, approved YouTube sources
- `ingestion`: raw candidates, artist seeds, chart sampling, YouTube matching jobs
- `moderation`: review actions, user quality reports, automatic blocking
- `quizzes`: questions, answer aliases, difficulty, quiz packs
- `rooms`: rooms, participants, game sessions, rounds, submissions, WebSocket flow

## Current Project State

The core game flow exists, and the backend data model was redesigned for a safer
ingestion pipeline. The project resumed on 2026-07-10 with Bugs artist seed
collection and artist-first YouTube discovery.

The current collection goal is not strict official-only sourcing. The practical
goal is to collect videos that are good enough for players to hear and guess:
official MVs, official audio, topic/art tracks, lyric videos, and original-audio
uploads can all be useful. Covers, karaoke, instrumental, remix/sped-up,
reaction, fancam, shorts-like edits, playlists, and medleys remain risky.

The latest design direction is:

```text
artist seeds
-> YouTube playable video discovery
-> review-friendly candidate storage
-> Song + YoutubeSource + QuizQuestion promotion
-> user report / admin correction loop
```

The earlier idea was to collect many song candidates from public chart pages and
then match every song to YouTube. That changed because YouTube Data API search
quota is the real bottleneck. With the default quota, `search.list` costs about
100 units per call, so only around 100 searches per day are practical.

The preferred direction is now artist-first:

1. Build an `ArtistSeed` queue from public chart pages.
2. Search YouTube by artist, for example `{artist} mv`.
3. Store playable-looking candidates broadly enough for review.
4. De-duplicate by YouTube video ID and normalized artist/title key.
5. Generate editable title/artist answer candidates.
6. Let admins approve, edit, reject, or merge duplicate candidates.

## Data Model Decisions

The catalog model was renamed around the actual domain:

- `Song`: canonical song data. This should be mostly immutable.
- `SongExternalId`: external provider IDs.
- `YoutubeSource`: playable YouTube video data, separate from the song.
- `RawCandidate`: raw song candidate data from ingestion.
- `ArtistSeed`: artist queue used for YouTube discovery.
- `QualityReport`: user report model; repeated reports can block a song/source.

Important policy decisions:

- `Song` is the song itself.
- `YoutubeSource` is a playable video for a song.
- Existing `Song` metadata should not be automatically overwritten.
- YouTube sources can be replaced or blocked when unavailable or incorrect.
- A playable quiz item must satisfy:

```text
QuizQuestion.status = approved
Song.approved = true
Song.playable = true
Song.blocked = false
YoutubeSource.status = approved
```

## Bugs Chart Policy

Bugs should not be treated as the canonical metadata provider.

The safer policy is to use Bugs only as a public chart sampling source for artist
seeds. The project intentionally avoids storing Bugs IDs, URLs, rankings, chart
periods, album names, release dates, images, lyrics, or raw HTML.

For artist seed collection, the DB stores only:

```text
source_type = b
raw_artist
raw_artist_key
display_artist
first_observed_year/month/sample_day
last_observed_year/month/sample_day
observed_count
observed_sample_count
observed_weight_score
status
```

The current `source_type = b` is intentionally short and internal.

The Bugs chart targets currently configured are:

```text
total
k_ballad
k_dance
k_folk
k_idol
k_hiphop
k_rnb
k_indie
ost
pop
pop_hiphop
pop_rnb
pop_rock
jpop
```

The latest intended collection split:

```text
Primary Korean-focused pool:
total k_ballad k_dance k_idol k_hiphop k_indie ost

Later:
pop pop_hiphop pop_rnb pop_rock jpop

Not currently prioritized:
k_folk k_rnb
```

## Artist Seed Scoring

The scoring logic was updated to avoid over-counting the same song across
multiple chart pages.

Aggregation unit:

```text
sample_date + artist_key + title_key
```

If the same song appears in multiple selected charts on the same sample date, it
counts once. The highest chart weight wins.

Current weights and limits:

```text
total:
  row_limit = 100
  weight = 3

domestic / etc:
  row_limit = 100
  weight = 1

overseas:
  row_limit = 20
  weight = 1
```

This means:

```text
Same artist, same song, same date, total + genre:
  item_count +1
  score +3

Same artist, different songs, same date:
  each song counts separately
```

The title key is used only during aggregation and is not stored on `ArtistSeed`.

## Useful Commands

Start services:

```powershell
docker compose up --build
```

Run migrations:

```powershell
docker compose run --rm backend python manage.py migrate
```

Collect test raw song candidates from the fixed sample dates:

```powershell
docker compose run --rm backend python manage.py collect_bugs_chart_samples --dry-run --delay 0.2
docker compose run --rm backend python manage.py collect_bugs_chart_samples --delay 0.2
```

Collect artist seeds for the current Korean-focused set:

```powershell
docker compose run --rm backend python manage.py collect_bugs_artist_seeds --backfill --charts total k_ballad k_dance k_idol k_hiphop k_indie ost --delay 1.5
```

Collect initial artist seeds from one quarterly representative Bugs weekly page
per quarter:

```powershell
docker compose run --rm backend python manage.py collect_bugs_quarterly_artist_seeds --dry-run --max-pages 1
docker compose run --rm backend python manage.py collect_bugs_quarterly_artist_seeds --start-year 2007 --end-year 2026 --rank-limit 100 --chart total --delay 1.5
```

The quarterly command samples March 15, June 15, September 15, and December 15
for each year, using the Bugs weekly chart page containing that date. Future
sample dates are skipped automatically.

Rank weights:

```text
1-10: +5
11-30: +3
31-100: +1
```

Collect the later overseas/J-POP set:

```powershell
docker compose run --rm backend python manage.py collect_bugs_artist_seeds --backfill --charts pop pop_hiphop pop_rnb pop_rock jpop --delay 1.5
```

Resume from a specific month:

```powershell
docker compose run --rm backend python manage.py collect_bugs_artist_seeds --backfill --start-month 2023-04 --charts total k_ballad k_dance k_idol k_hiphop k_indie ost --delay 1.5
```

Check top artist seeds:

```powershell
docker compose run --rm backend python manage.py shell -c "from apps.ingestion.models import ArtistSeed; [print(s.display_artist, s.observed_weight_score, s.observed_count, s.observed_sample_count) for s in ArtistSeed.objects.order_by('-observed_weight_score')[:20]]"
```

YouTube matching command, prepared but not fully used yet:

```powershell
docker compose run --rm backend python manage.py match_youtube_sources --dry-run --limit 20
```

This requires one or more YouTube Data API keys:

```text
YOUTUBE_API_KEY1=
YOUTUBE_API_KEY2=
```

Artist-first YouTube MV discovery:

```powershell
docker compose run --rm backend python manage.py discover_youtube_artist_videos --dry-run --limit 3
docker compose run --rm backend python manage.py discover_youtube_artist_videos --limit 10
docker compose run --rm backend python manage.py discover_youtube_artist_videos --all --max-pages 3 --page-size 20 --continue-min 13
```

The discovery command searches YouTube with:

```text
{artist} mv
```

Default pagination policy:

```text
page_size = 20
score_threshold = 70
continue_min = 13
```

If 13 or more of the 20 results score at least 70, the command collects the
next page, up to `--max-pages`.

Progress is tracked with `YoutubeArtistDiscoveryCursor` in Django admin. The
artist queue itself is `ArtistSeed`: pending artists have `status = pending`,
and searched artists are updated to `status = youtube_searched`. Running the
same command the next day continues with the remaining pending artists.

When multiple YouTube keys are configured, requests start with the first key and
fall through to the next key if the current key hits a quota-style 403/429 error.
If every configured key is exhausted, the command stops cleanly and leaves the
current and remaining artists in `pending` state for the next run.

Qualified videos are stored in `DiscoveredYoutubeVideo` with the minimum
operational metadata needed for the quiz catalog pass:

```text
song_title
artist_name
youtube_url
uploaded_year
uploaded_month
```

The table also keeps `youtube_title`, `video_id`, `channel_title`, and
`official_score` for review and deduplication. The release year/month currently
comes from the YouTube upload date.

Promote discovered videos into playable quiz questions:

```powershell
docker compose run --rm backend python manage.py promote_discovered_youtube_videos --dry-run
docker compose run --rm backend python manage.py promote_discovered_youtube_videos
```

Default promotion policy:

```text
source rows: DiscoveredYoutubeVideo.status = discovered
minimum score: official_score >= 70
target pack: Auto Discovered Songs
question status: approved
```

Promotion creates or reuses `Artist`, `Song`, `YoutubeSource`, `QuizQuestion`,
`QuizAnswerAlias`, and `QuizPackQuestion`. Rows with missing title/artist,
unknown source type, too-short videos, very long videos, or YouTube IDs already
matched to another song are left as `review_required` for admin review.

Quality reports currently use a threshold of 3 reports. When a song or YouTube
source reaches the threshold, related approved questions are moved back to
`needs_review` and a `ReviewAction` is created with
`reason = quality_report_threshold`.

Probe artist query variants without reusing API calls:

```powershell
docker compose run --rm backend python manage.py probe_youtube_artist_queries --limit 10 --max-results 25
```

The probe command caches raw YouTube `search.list` responses under
`backend/data/youtube_query_probe/top10_basic_vs_negative/raw/` and reuses those
JSON files on later runs unless `--force-fetch` is passed. It also writes
`artists.csv`, `query_summary.csv`, `query_results.csv`, `manifest.json`, and
`report.md`.

## Resume Log 2026-07-10

Local MVP checks passed:

```text
docker compose up --build -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_sample_questions
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run --noinput
docker compose exec backend python -m ruff check apps --exclude migrations
docker compose exec frontend npm run build
docker compose exec backend python manage.py test
```

The sample game flow was verified through API calls: room creation, game start,
round start via Celery, answer submission, scoring, automatic finish, and
WebSocket `room_state` delivery.

Bugs quarterly artist seeds were collected with:

```powershell
docker compose exec backend python manage.py collect_bugs_quarterly_artist_seeds --start-year 2024 --end-year 2026 --rank-limit 100 --chart total --delay 1.5 --max-pages 8
```

Result:

```text
ArtistSeed total = 146
pending before YouTube discovery = 146
top seeds included DAY6, NewJeans, aespa, IVE, IU, ROSÉ, G-DRAGON, JENNIE,
LE SSERAFIM, and i-dle.
```

YouTube query probing compared `{artist} mv` against a negative-term query for
the top 10 seeds. The basic query was preferred: the negative-term query produced
more shorts/fan/playlist-like contamination despite looking numerically strong.
Probe outputs are stored under:

```text
backend/data/youtube_query_probe/top10_basic_vs_negative/
```

The first full artist discovery run used:

```powershell
docker compose exec backend python manage.py discover_youtube_artist_videos --all --max-pages 3 --page-size 20 --continue-min 13
```

Result before YouTube quota exhaustion:

```text
processed artists = 54
searched pages = 86
qualified videos = 923
stored videos = 923
review videos = 152
failed = 0
quota_exhausted = 1

ArtistSeed total = 146
youtube_searched = 54
pending = 92
DiscoveredYoutubeVideo total = 923
discovered = 840
review_required = 83
cursor status = active
```

The first automatic promotion run used:

```powershell
docker compose exec backend python manage.py promote_discovered_youtube_videos
```

Result:

```text
processed discovered videos = 840
promoted = 831
duplicates linked to pack = 3
new songs = 823
new YouTube sources = 831
new quiz questions = 831
Auto Discovered Songs pack questions = 834
playable approved questions in pack = 834
review_required after promotion = 89
```

The 6 rows newly left for review were short videos, very long videos, or a
YouTube ID already matched to an existing sample song.

Next run can use the same discovery command; it will continue with pending
artists such as ZICO, DOYOUNG, JAESSBEE, MAKTUB, Taylor Swift, Lee Young Ji,
GroovyRoom, Mariah Carey, Ariana Grande, and Hanroro.

Recommended next implementation pass:

1. Build an admin-friendly candidate review loop that lets a reviewer listen,
   guess, approve, edit title/artist, reject, or merge duplicates.
2. Test the `Auto Discovered Songs` pack through the live game flow and mark
   bad items through reports or admin review.
3. Strengthen duplicate grouping and answer alias generation after observing
   real quiz misses.
4. Relax candidate storage around lyric/topic/playable original-audio videos,
   while still strongly excluding cover, karaoke, instrumental, remix, reaction,
   fancam, shorts-like edits, playlists, and medleys.

## Verification Notes

Recent checks that passed:

```powershell
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py makemigrations --check --dry-run --noinput
docker compose run --rm backend python -m ruff check apps --exclude migrations
docker compose run --rm backend python manage.py test
```

There are currently no Django tests, so `manage.py test` reports `0 tests`.

Running `ruff check .` may fail on historical migration files with long generated
lines. Use `ruff check apps --exclude migrations` for application code.

## Pause Notes

The project is paused mainly because YouTube Data API access and quota limits
need a more focused implementation pass.

Recommended next steps when resuming:

1. Add or confirm `YOUTUBE_API_KEY`.
2. Finish artist-first YouTube discovery.
3. Store artist-level YouTube search attempts on `ArtistSeed`.
4. Promote only clearly official videos to `Song` and `YoutubeSource`.
5. Keep ambiguous videos in review.
6. Add small tests for parser aggregation and YouTube decision scoring.
