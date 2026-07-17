# Guess Song Session Handoff

Date: 2026-07-16

## Current State

- Docker dev stack was used during this session.
- Backend and frontend checks passed after the latest changes:
  - `docker compose exec -T backend python manage.py check`
  - `docker compose exec -T frontend npm run build`
- The worktree is dirty. Do not revert unrelated changes.

## Music Collection

- Existing artist seed pool has been fully processed.
- Final observed counts after collection:
  - `ArtistSeed`: 146 total, all `youtube_searched`
  - `Song`: 1955
  - `YoutubeSource`: 1974
  - `QuizQuestion`: 1974
  - `Auto Discovered Songs`: 1972 linked questions
  - `DiscoveredYoutubeVideo review_required`: 264
- YouTube source embeddability check was run on approved sources:
  - Checked 1974
  - Embeddable 1974
  - Not embeddable 0
  - Missing 0

## Quiz Packs And Scopes

- Added/used `backend/apps/quizzes/management/commands/sync_quiz_collections.py`.
- It syncs:
  - answer aliases
  - yearly quiz packs
  - artist quiz packs
- Current generated packs:
  - 18 yearly packs
  - 135 artist packs
- Added `/api/quiz-scopes`.
  - Returns actual playable years and artists from DB.
  - Last check returned 18 years and 372 artists.
- Frontend room settings now load these dynamic scope options instead of hardcoded artist/year lists.

## Answer Alias And Matching

- `backend/apps/core/text.py` now normalizes answers by:
  - NFKC
  - removing bracketed text
  - casefolding
  - removing punctuation
  - removing all whitespace
- Matching remains local DB alias exact-match after normalization.
- AI is not used in realtime answer checking.
- Alias generation was expanded:
  - bracket contents
  - bracket removed forms
  - split aliases
  - selected English/Korean pronunciation aliases
- Example generated aliases:
  - `FIRE` -> `파이어`
  - `NewJeans` -> `뉴진스`
  - `BTS` -> `비티에스`
  - `IVE` -> `아이브`
  - `Lady Gaga` -> `레이디 가가`

## Room Settings And Question Selection

- `ALL_RANDOM` now shuffles approved questions before selecting.
- `YEAR` and `ARTIST` scopes are applied in backend question query before game start.
- Default pack selection in frontend now chooses the public pack with the largest approved question count.
- Room setting API validates `question_scope_type` and `question_scope_value`.

## Round Playback

- Round time options changed to:
  - 8 seconds
  - 16 seconds
  - 30 seconds
- Hidden listening playback is split into two segments with a 1 second pause:
  - 8 sec = 4 + pause + 4
  - 16 sec = 8 + pause + 8
  - 30 sec = 15 + pause + 15
- Hidden player uses YouTube IFrame API for segment control.
- Reveal player still uses normal iframe.
- Backend serializes `playback_segments` for current round.
- Round end task schedules `round_time_limit_sec + 1` seconds to account for the pause.

## YouTube Playback Safety

- Search already used `videoEmbeddable=true`; now also uses `videoSyndicated=true`.
- `VideoCandidate` includes `embeddable`.
- If `embeddable` is false, candidates are rejected before promotion.
- Added management command:
  - `check_youtube_source_embeddability`
- Frontend hidden YouTube player now detects YouTube error codes:
  - `101`/`150`: external playback restricted
  - `100`: unavailable video

## Answer Submission Performance

- Enter submit now clears the input immediately before waiting for API response.
- Submit API no longer returns full room state for normal answers.
- Submit response returns:
  - answer result
  - newly created answer submission payload
  - participant/team score
  - full room only for special cases like game finish
- Frontend applies this small response immediately for fast chat/score feedback.
- Full room sync is still handled by WebSocket.
- Broadcast after answer submission is now delegated through Celery task:
  - `broadcast_room_state_task`

## Fixed Bugs

- Artist-only correct answers in `TITLE_AND_ARTIST` mode now show score messages.
- Cause was duplicate display merging dropping the later artist scoring submission.
- Fixed by merging adjacent same-answer field submissions while preserving score.

## AI Discussion And Future Direction

User is considering OpenAI API for offline/batch catalog cleanup, not realtime answer judging.

Desired AI tasks:

- Detect cover/live/fan/playlist/compilation/unusable candidates.
- Normalize canonical title and artist.
- Deduplicate songs.
- Keep only highest quality source for a duplicate song.
- Generate title and artist answer aliases.

Important design conclusion:

- Realtime game should continue using local DB aliases only.
- AI should produce patch proposals, not directly mutate final game data.
- Monthly full DB snapshot batch is likely better for current project stage than per-candidate processing.
- Per-candidate processing would need a synced catalog store or vector/file retrieval, but that adds complexity.

Possible future models/tables:

- `AiCatalogSnapshot`
- `AiCatalogPatch`
- or `GeneratedAnswerAlias`

Possible future commands:

- `export_ai_catalog_snapshot`
- `run_ai_catalog_cleanup`
- `apply_ai_catalog_patches`

## Follow-Up Recommendations

1. Commit current changes after review.
2. Add tests around:
   - answer normalization
   - artist/title field submission merge
   - scope filtering
   - playback segment generation
3. Consider converting artist scope dropdown to searchable combobox because there are 372 artist options.
4. Consider monthly AI catalog cleanup pipeline only after DB patch/review model is designed.
