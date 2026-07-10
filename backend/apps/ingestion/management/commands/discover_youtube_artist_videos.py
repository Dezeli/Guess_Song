import re
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.ingestion.management.commands.collect_bugs_chart_samples import normalize_raw_key
from apps.ingestion.models import (
    ArtistSeed,
    DiscoveredYoutubeVideo,
    IngestionJob,
    IngestionLog,
    YoutubeArtistDiscoveryCursor,
)
from apps.ingestion.youtube_matching import (
    ARTIST_DISCOVERY_CONTINUE_MIN_MATCHES,
    ARTIST_DISCOVERY_PAGE_SIZE,
    ARTIST_DISCOVERY_SCORE_THRESHOLD,
    REVIEW_THRESHOLD,
    YouTubeQuotaExhausted,
    build_artist_mv_query,
    score_artist_video,
    search_artist_mv_videos,
)


class Command(BaseCommand):
    help = "Discover likely official YouTube MV candidates from artist seed searches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cursor",
            default="default",
            help="Persistent cursor name used to track where artist discovery stopped.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of artist seeds to process.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Process every pending artist seed until the queue or API quota is exhausted.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=3,
            help="Maximum YouTube search pages to inspect per artist.",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=ARTIST_DISCOVERY_PAGE_SIZE,
            help="YouTube search results per page. YouTube allows up to 50.",
        )
        parser.add_argument(
            "--score-threshold",
            type=int,
            default=ARTIST_DISCOVERY_SCORE_THRESHOLD,
            help="Minimum official score for a result to count as a strong artist hit.",
        )
        parser.add_argument(
            "--continue-min",
            type=int,
            default=ARTIST_DISCOVERY_CONTINUE_MIN_MATCHES,
            help="Collect the next page when this many results meet the score threshold.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Search and log results without updating ArtistSeed rows.",
        )

    def handle(self, *args, **options):
        cursor_name = options["cursor"]
        process_all = options["all"] or options["limit"] <= 0
        limit = None if process_all else max(options["limit"], 1)
        max_pages = max(options["max_pages"], 1)
        page_size = min(max(options["page_size"], 1), 50)
        score_threshold = min(max(options["score_threshold"], 0), 100)
        continue_min = min(max(options["continue_min"], 1), page_size)
        dry_run = options["dry_run"]

        cursor, _ = YoutubeArtistDiscoveryCursor.objects.get_or_create(
            name=cursor_name,
            defaults={
                "source_type": ArtistSeed.SourceType.B,
                "params": {
                    "query_template": "{artist} mv",
                    "page_size": page_size,
                    "score_threshold": score_threshold,
                    "continue_min": continue_min,
                },
            },
        )
        if cursor.status == YoutubeArtistDiscoveryCursor.Status.PAUSED:
            raise RuntimeError(f'YouTube artist discovery cursor "{cursor.name}" is paused.')

        run_started_at = timezone.now()
        if not dry_run:
            cursor.status = YoutubeArtistDiscoveryCursor.Status.ACTIVE
            cursor.last_run_started_at = run_started_at
            cursor.last_run_finished_at = None
            cursor.params = {
                **cursor.params,
                "query_template": "{artist} mv",
                "page_size": page_size,
                "score_threshold": score_threshold,
                "continue_min": continue_min,
                "max_pages": max_pages,
            }
            cursor.save(
                update_fields=[
                    "status",
                    "last_run_started_at",
                    "last_run_finished_at",
                    "params",
                    "updated_at",
                ]
            )

        job = IngestionJob.objects.create(
            job_type="youtube_artist_discovery",
            status=IngestionJob.Status.RUNNING,
            params={
                "cursor": cursor_name,
                "limit": limit,
                "all": process_all,
                "max_pages": max_pages,
                "page_size": page_size,
                "score_threshold": score_threshold,
                "continue_min": continue_min,
                "query_template": "{artist} mv",
                "dry_run": dry_run,
            },
            started_at=run_started_at,
        )

        counters = {
            "processed": 0,
            "searched_pages": 0,
            "qualified_videos": 0,
            "review_videos": 0,
            "stored_videos": 0,
            "failed": 0,
            "quota_exhausted": 0,
        }

        seeds = ArtistSeed.objects.filter(status=ArtistSeed.Status.PENDING).order_by(
            "-observed_weight_score",
            "-observed_count",
            "id",
        )
        if not process_all:
            seeds = seeds[:limit]

        try:
            for seed in seeds:
                try:
                    discovery = discover_artist_seed(
                        seed=seed,
                        max_pages=max_pages,
                        page_size=page_size,
                        score_threshold=score_threshold,
                        continue_min=continue_min,
                    )
                    counters["processed"] += 1
                    counters["searched_pages"] += len(discovery["pages"])
                    counters["qualified_videos"] += discovery["qualified_video_count"]
                    counters["review_videos"] += discovery["review_video_count"]

                    if not dry_run:
                        with transaction.atomic():
                            locked_seed = ArtistSeed.objects.select_for_update().get(id=seed.id)
                            locked_cursor = (
                                YoutubeArtistDiscoveryCursor.objects.select_for_update().get(
                                    id=cursor.id
                                )
                            )
                            payload = {
                                **locked_seed.metadata_payload,
                                "youtube_artist_discovery_summary": _discovery_summary(discovery),
                            }
                            locked_seed.status = ArtistSeed.Status.YOUTUBE_SEARCHED
                            locked_seed.youtube_search_attempt_count += 1
                            locked_seed.last_youtube_search_attempt_at = timezone.now()
                            locked_seed.metadata_payload = payload
                            locked_seed.save(
                                update_fields=[
                                    "status",
                                    "youtube_search_attempt_count",
                                    "last_youtube_search_attempt_at",
                                    "metadata_payload",
                                    "updated_at",
                                ]
                            )
                            locked_cursor.last_artist_seed = locked_seed
                            locked_cursor.last_artist_name = locked_seed.display_artist
                            locked_cursor.last_artist_key = locked_seed.raw_artist_key
                            locked_cursor.processed_count += 1
                            locked_cursor.save(
                                update_fields=[
                                    "last_artist_seed",
                                    "last_artist_name",
                                    "last_artist_key",
                                    "processed_count",
                                    "updated_at",
                                ]
                            )
                            counters["stored_videos"] += _store_discovered_videos(
                                seed=locked_seed,
                                job=job,
                                discovery=discovery,
                                score_threshold=score_threshold,
                            )

                    IngestionLog.objects.create(
                        job=job,
                        level=IngestionLog.Level.INFO,
                        message="Discovered YouTube artist videos.",
                        context={
                            "artist_seed_id": seed.id,
                            "artist": seed.display_artist,
                            "pages": len(discovery["pages"]),
                            "qualified_video_count": discovery["qualified_video_count"],
                            "stop_reason": discovery["stop_reason"],
                            "dry_run": dry_run,
                        },
                    )
                except YouTubeQuotaExhausted as exc:
                    counters["quota_exhausted"] = 1
                    IngestionLog.objects.create(
                        job=job,
                        level=IngestionLog.Level.WARNING,
                        message="Stopped YouTube artist discovery because API quota is exhausted.",
                        context={
                            "artist_seed_id": seed.id,
                            "artist": seed.display_artist,
                            "error": str(exc),
                            "remaining_pending_count": ArtistSeed.objects.filter(
                                status=ArtistSeed.Status.PENDING,
                            ).count(),
                        },
                    )
                    break
                except Exception as exc:
                    counters["processed"] += 1
                    counters["failed"] += 1
                    if not dry_run:
                        YoutubeArtistDiscoveryCursor.objects.filter(id=cursor.id).update(
                            failed_count=F("failed_count") + 1,
                            updated_at=timezone.now(),
                        )
                    IngestionLog.objects.create(
                        job=job,
                        level=IngestionLog.Level.ERROR,
                        message="Failed to discover YouTube artist videos.",
                        context={
                            "artist_seed_id": seed.id,
                            "artist": seed.display_artist,
                            "error": str(exc),
                        },
                    )

            job.status = (
                IngestionJob.Status.FAILED
                if counters["processed"] and counters["failed"] == counters["processed"]
                else IngestionJob.Status.SUCCEEDED
            )
            job.total_count = counters["processed"]
            job.success_count = counters["processed"] - counters["failed"]
            job.fail_count = counters["failed"]
            job.finished_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "total_count",
                    "success_count",
                    "fail_count",
                    "finished_at",
                ]
            )
            if not dry_run:
                cursor = YoutubeArtistDiscoveryCursor.objects.get(id=cursor.id)
                if counters["quota_exhausted"]:
                    cursor.status = YoutubeArtistDiscoveryCursor.Status.ACTIVE
                elif counters["processed"] == 0:
                    cursor.status = YoutubeArtistDiscoveryCursor.Status.COMPLETED
                else:
                    cursor.status = YoutubeArtistDiscoveryCursor.Status.ACTIVE
                cursor.last_run_finished_at = timezone.now()
                cursor.save(update_fields=["status", "last_run_finished_at", "updated_at"])
        except Exception as exc:
            job.status = IngestionJob.Status.FAILED
            job.error_message = str(exc)
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error_message", "finished_at"])
            raise

        self.stdout.write(
            self.style.SUCCESS(
                "Processed {processed}, searched_pages {searched_pages}, "
                "qualified_videos {qualified_videos}, stored_videos {stored_videos}, "
                "review_videos {review_videos}, failed {failed}, "
                "quota_exhausted {quota_exhausted}.".format(**counters)
            )
        )


def discover_artist_seed(
    seed: ArtistSeed,
    max_pages: int,
    page_size: int,
    score_threshold: int,
    continue_min: int,
) -> dict:
    artist = seed.display_artist or seed.raw_artist
    query = build_artist_mv_query(artist)
    searched_at = timezone.now()
    page_token = None
    pages = []
    qualified_video_count = 0
    review_video_count = 0
    stop_reason = "max_pages"

    for page_number in range(1, max_pages + 1):
        search_page = search_artist_mv_videos(
            artist=artist,
            max_results=page_size,
            page_token=page_token,
        )
        scored_videos = [_serialize_scored_video(video, artist) for video in search_page.videos]
        qualified_count = sum(
            1 for video in scored_videos if video["official_score"] >= score_threshold
        )
        review_count = sum(
            1
            for video in scored_videos
            if REVIEW_THRESHOLD <= video["official_score"] < score_threshold
        )
        qualified_video_count += qualified_count
        review_video_count += review_count

        pages.append(
            {
                "page": page_number,
                "result_count": len(scored_videos),
                "qualified_count": qualified_count,
                "review_count": review_count,
                "next_page_token_present": bool(search_page.next_page_token),
                "total_results": search_page.total_results,
                "videos": scored_videos,
            }
        )

        if not search_page.next_page_token:
            stop_reason = "no_next_page"
            break
        if qualified_count < continue_min:
            stop_reason = "qualified_count_below_continue_min"
            break
        page_token = search_page.next_page_token

    return {
        "query": query,
        "searched_at": searched_at.isoformat(),
        "score_threshold": score_threshold,
        "continue_min": continue_min,
        "page_size": page_size,
        "qualified_video_count": qualified_video_count,
        "review_video_count": review_video_count,
        "stop_reason": stop_reason,
        "pages": pages,
    }


def _serialize_scored_video(video, artist: str) -> dict:
    decision = score_artist_video(video, artist=artist)
    return {
        "video_id": video.video_id,
        "title": video.title,
        "channel_title": video.channel_title,
        "channel_id": video.channel_id,
        "duration_seconds": video.duration_seconds,
        "view_count": video.view_count,
        "published_at": video.published_at,
        "source_type": decision.source_type,
        "official_score": decision.official_score,
        "reason": decision.reason,
        "action": decision.action,
    }


def _store_discovered_videos(
    seed: ArtistSeed,
    job: IngestionJob,
    discovery: dict,
    score_threshold: int,
) -> int:
    stored_count = 0
    for page in discovery["pages"]:
        for video in page["videos"]:
            if video["official_score"] < REVIEW_THRESHOLD:
                continue
            status = (
                DiscoveredYoutubeVideo.Status.DISCOVERED
                if video["official_score"] >= score_threshold
                else DiscoveredYoutubeVideo.Status.REVIEW_REQUIRED
            )

            uploaded_year, uploaded_month = _published_year_month(video["published_at"])
            artist_name, song_title = _infer_artist_and_song_title(
                video["title"],
                seed.display_artist or seed.raw_artist,
            )
            created = _upsert_discovered_video(
                seed=seed,
                job=job,
                video=video,
                artist_name=artist_name,
                song_title=song_title,
                uploaded_year=uploaded_year,
                uploaded_month=uploaded_month,
                status=status,
                discovery_query=discovery["query"],
            )
            if created:
                stored_count += 1
    return stored_count


def _upsert_discovered_video(
    seed: ArtistSeed,
    job: IngestionJob,
    video: dict,
    artist_name: str,
    song_title: str,
    uploaded_year: int | None,
    uploaded_month: int | None,
    status: str,
    discovery_query: str,
) -> bool:
    normalized_artist_name = normalize_raw_key(artist_name)
    normalized_song_title = normalize_raw_key(_canonical_song_title(song_title))
    artist_title_key = f"{normalized_artist_name}:{normalized_song_title}"
    defaults = {
        "artist_seed": seed,
        "job": job,
        "song_title": song_title,
        "artist_name": artist_name,
        "normalized_song_title": normalized_song_title,
        "normalized_artist_name": normalized_artist_name,
        "artist_title_key": artist_title_key,
        "youtube_url": f"https://www.youtube.com/watch?v={video['video_id']}",
        "youtube_title": video["title"],
        "channel_title": video["channel_title"],
        "channel_id": video["channel_id"],
        "uploaded_year": uploaded_year,
        "uploaded_month": uploaded_month,
        "official_score": video["official_score"],
        "source_type": video["source_type"] or "",
        "status": status,
        "raw_payload": {
            "reason": video["reason"],
            "action": video["action"],
            "duration_seconds": video["duration_seconds"],
            "view_count": video["view_count"],
            "published_at": video["published_at"],
            "discovery_query": discovery_query,
        },
    }

    existing_by_video = DiscoveredYoutubeVideo.objects.filter(video_id=video["video_id"]).first()
    if existing_by_video:
        _apply_video_defaults(existing_by_video, defaults)
        existing_by_video.save()
        return False

    existing_by_song = DiscoveredYoutubeVideo.objects.filter(
        artist_title_key=artist_title_key
    ).first()
    if existing_by_song:
        if _candidate_is_better(existing_by_song, defaults):
            _apply_video_defaults(existing_by_song, defaults)
            existing_by_song.video_id = video["video_id"]
            existing_by_song.save()
        return False

    DiscoveredYoutubeVideo.objects.create(video_id=video["video_id"], **defaults)
    return True


def _apply_video_defaults(instance: DiscoveredYoutubeVideo, defaults: dict) -> None:
    for field, value in defaults.items():
        setattr(instance, field, value)


def _candidate_is_better(existing: DiscoveredYoutubeVideo, candidate: dict) -> bool:
    existing_rank = _status_rank(existing.status)
    candidate_rank = _status_rank(candidate["status"])
    if candidate_rank != existing_rank:
        return candidate_rank > existing_rank
    if candidate["official_score"] != existing.official_score:
        return candidate["official_score"] > existing.official_score
    existing_views = existing.raw_payload.get("view_count") or 0
    candidate_views = candidate["raw_payload"].get("view_count") or 0
    return candidate_views > existing_views


def _status_rank(status: str) -> int:
    if status == DiscoveredYoutubeVideo.Status.DISCOVERED:
        return 2
    if status == DiscoveredYoutubeVideo.Status.REVIEW_REQUIRED:
        return 1
    return 0


def _published_year_month(published_at: str | None) -> tuple[int | None, int | None]:
    if not published_at:
        return None, None
    try:
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    return parsed.year, parsed.month


def _guess_song_title(youtube_title: str, artist_name: str) -> str:
    title = _strip_leading_metadata(youtube_title)
    quoted = _extract_quoted_title(title)
    if quoted:
        title = quoted
    title = _remove_artist_aliases(title, artist_name)
    title = re.sub(r"(?i)\bofficial\b", " ", title)
    title = re.sub(r"(?i)\bm/?v\b|\bmusic video\b|\bmv\b", " ", title)
    title = re.sub(r"(?i)\bofficial audio\b|\baudio\b", " ", title)
    title = re.sub(r"(?i)\bwith\s+android\b", " ", title)
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = _remove_version_parentheses(title)
    title = _remove_inline_version_terms(title)
    title = title.replace("'", " ").replace('"', " ")
    title = title.replace("‘", " ").replace("’", " ")
    title = title.replace("“", " ").replace("”", " ")
    title = re.sub(r"[-_|:]+", " ", title)
    title = " ".join(title.split())
    return title[:255] or youtube_title[:255]


def _canonical_song_title(song_title: str) -> str:
    title = song_title
    title = re.sub(r"(?i)\bperformance\s+(?:ver|version|video)\b", " ", title)
    title = re.sub(r"(?i)\bdance\s+(?:ver|version|practice)\b", " ", title)
    title = re.sub(r"(?i)\bchoreography\s+video\b", " ", title)
    title = re.sub(r"(?i)\b(?:drama|special)\s+(?:ver|version|clip)\b", " ", title)
    title = re.sub(r"(?i)\bvisualizer\b", " ", title)
    title = re.sub(r"(?i)\bside\s+[ab]\b", " ", title)
    title = re.sub(r"(?i)\bpart\s+\d+\b", " ", title)
    title = re.sub(r"(?i)\b\d+k\b|\b\d+fps\b", " ", title)
    return " ".join(title.split())


def _infer_artist_and_song_title(youtube_title: str, seed_artist_name: str) -> tuple[str, str]:
    normalized_title = youtube_title.strip()
    cleaned_title = _strip_leading_metadata(normalized_title)
    reverse = _extract_title_artist_pattern(cleaned_title, seed_artist_name)
    if reverse:
        artist_name, song_title = reverse
        return artist_name[:255], _guess_song_title(song_title, artist_name)
    lead_artist = _extract_lead_artist(cleaned_title)
    if lead_artist:
        remaining_title = _remove_lead_artist_prefix(cleaned_title, lead_artist)
        remaining_title = _strip_leading_parenthetical_alias(remaining_title)
        return lead_artist[:255], _guess_song_title(remaining_title, lead_artist)
    underscore_artist = _extract_underscore_lead_artist(cleaned_title)
    if underscore_artist:
        remaining_title = cleaned_title.split("_", 1)[1]
        return underscore_artist[:255], _guess_song_title(remaining_title, underscore_artist)
    return seed_artist_name[:255], _guess_song_title(cleaned_title, seed_artist_name)


def _extract_title_artist_pattern(title: str, seed_artist_name: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in re.split(r"\s+-\s+", title) if part.strip()]
    if len(parts) < 2:
        return None
    first, second = parts[0], parts[1]
    if not _text_has_artist_alias(second, seed_artist_name):
        return None
    if _text_has_artist_alias(first, seed_artist_name):
        return None
    song_title = first
    artist_name = _clean_artist_from_segment(second, seed_artist_name)
    return artist_name, song_title


def _extract_lead_artist(title: str) -> str:
    for separator in [" - ", " – ", " — ", " _ ", " | "]:
        if separator not in title:
            continue
        lead = title.split(separator, 1)[0]
        lead = _clean_lead_artist(lead)
        if _looks_like_artist_name(lead):
            return lead
    return ""


def _extract_underscore_lead_artist(title: str) -> str:
    if "_" not in title:
        return ""
    lead = title.split("_", 1)[0]
    lead = _clean_lead_artist(lead)
    if _looks_like_artist_name(lead):
        return lead
    return ""


def _clean_lead_artist(value: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = value.replace("[MV]", " ").replace("[M/V]", " ")
    value = value.strip(" '\"")
    return " ".join(value.split())


def _looks_like_artist_name(value: str) -> bool:
    if not value:
        return False
    compact = value.replace(" ", "")
    if len(compact) < 2 or len(value) > 80:
        return False
    blocked_words = {"official", "music", "video", "mv", "ost", "part"}
    return not any(word in value.casefold().split() for word in blocked_words)


def _strip_leading_metadata(value: str) -> str:
    return re.sub(r"^\s*\[(?:mv|m/v|official mv|official music video)\]\s*", "", value, flags=re.I)


def _strip_leading_parenthetical_alias(value: str) -> str:
    return re.sub(r"^\s*\([^)]*\)\s*(?:[-_|:]+|_)?\s*", "", value).strip()


def _remove_lead_artist_prefix(title: str, lead_artist: str) -> str:
    pattern = rf"^\s*{re.escape(lead_artist)}\s*(?:[-_–—|:]+)?\s*"
    return re.sub(pattern, " ", title, flags=re.I).strip()


def _extract_quoted_title(title: str) -> str:
    patterns = [
        r"'([^']+)'",
        r'"([^"]+)"',
        r"‘([^’]+)’",
        r"“([^”]+)”",
    ]
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(1).strip()
    return ""


def _remove_artist_aliases(title: str, artist_name: str) -> str:
    aliases = _artist_aliases_for_title(artist_name)
    for alias in sorted(aliases, key=len, reverse=True):
        title = re.sub(rf"(?i)(^|\s){re.escape(alias)}(?=\s|$)", " ", title)
    return title


def _artist_aliases_for_title(artist_name: str) -> set[str]:
    aliases = {artist_name}
    aliases.update(part for part in re.split(r"\s*[()/,&]\s*", artist_name) if part.strip())
    for match in re.findall(r"\(([^)]*)\)|\[([^\]]*)\]", artist_name):
        aliases.update(part for part in match if part)
    return {" ".join(alias.split()) for alias in aliases if len(alias.strip()) >= 2}


def _text_has_artist_alias(text: str, artist_name: str) -> bool:
    normalized_text = normalize_raw_key(text)
    for alias in _artist_aliases_for_title(artist_name):
        normalized_alias = normalize_raw_key(alias)
        if normalized_alias and normalized_alias in normalized_text:
            return True
    return False


def _clean_artist_from_segment(segment: str, fallback_artist_name: str) -> str:
    aliases = _artist_aliases_for_title(fallback_artist_name)
    for alias in sorted(aliases, key=len, reverse=True):
        if normalize_raw_key(alias) in normalize_raw_key(segment):
            return alias
    return fallback_artist_name


def _remove_version_parentheses(title: str) -> str:
    def replace(match):
        inner = match.group(1)
        if re.search(
            r"(?i)\b(?:ver|version|side|part|feat|prod|ost|special|drama|performance|dance)\b",
            inner,
        ):
            return " "
        return f"({inner})"

    return re.sub(r"\(([^)]*)\)", replace, title)


def _remove_inline_version_terms(title: str) -> str:
    title = re.sub(r"(?i)\bside\s+[ab]\b", " ", title)
    title = re.sub(r"(?i)\bpart\s+\d+\b", " ", title)
    title = re.sub(r"(?i)\bost\b.*", " ", title)
    title = re.sub(r"(?i)\b\d+k\b|\b\d+fps\b", " ", title)
    return title


def _discovery_summary(discovery: dict) -> dict:
    return {
        "query": discovery["query"],
        "searched_at": discovery["searched_at"],
        "score_threshold": discovery["score_threshold"],
        "continue_min": discovery["continue_min"],
        "page_size": discovery["page_size"],
        "qualified_video_count": discovery["qualified_video_count"],
        "review_video_count": discovery["review_video_count"],
        "stop_reason": discovery["stop_reason"],
        "page_count": len(discovery["pages"]),
    }
