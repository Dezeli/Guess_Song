import re
from dataclasses import dataclass
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.catalog.models import Artist, Song, SongArtist, YoutubeSource
from apps.core.text import normalize_answer
from apps.ingestion.models import DiscoveredYoutubeVideo, IngestionJob, IngestionLog
from apps.quizzes.models import QuizAnswerAlias, QuizPack, QuizPackQuestion, QuizQuestion

DEFAULT_MIN_SCORE = 70
DEFAULT_PACK_NAME = "Auto Discovered Songs"
MIN_PLAYABLE_DURATION_SECONDS = 45
MAX_PLAYABLE_DURATION_SECONDS = 15 * 60
DEFAULT_PLAY_DURATION_SECONDS = 20

TITLE_REVIEW_KEYS = {
    "mv",
    "m v",
    "music video",
    "official",
    "official mv",
    "official music video",
    "official audio",
    "video",
}

SOURCE_TYPE_PRIORITIES = {
    YoutubeSource.SourceType.OFFICIAL_MV: 10,
    YoutubeSource.SourceType.OFFICIAL_AUDIO: 20,
    YoutubeSource.SourceType.TOPIC_ART_TRACK: 30,
    YoutubeSource.SourceType.LABEL_CHANNEL: 40,
    YoutubeSource.SourceType.ARTIST_CHANNEL: 50,
}


@dataclass(frozen=True)
class PromotionResult:
    counter: str
    reason: str = ""
    song_created: bool = False
    source_created: bool = False
    question_created: bool = False
    pack_link_created: bool = False


class Command(BaseCommand):
    help = "Promote discovered YouTube videos into playable quiz questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of discovered videos to process. 0 means no limit.",
        )
        parser.add_argument(
            "--min-score",
            type=int,
            default=DEFAULT_MIN_SCORE,
            help="Minimum official score for automatic promotion.",
        )
        parser.add_argument(
            "--quiz-pack-name",
            default=DEFAULT_PACK_NAME,
            help="Quiz pack that receives promoted questions.",
        )
        parser.add_argument(
            "--private-pack",
            action="store_true",
            help="Create the target quiz pack as private if it does not exist.",
        )
        parser.add_argument(
            "--question-status",
            choices=[
                QuizQuestion.Status.APPROVED,
                QuizQuestion.Status.NEEDS_REVIEW,
            ],
            default=QuizQuestion.Status.APPROVED,
            help="Status to assign to newly promoted questions.",
        )
        parser.add_argument(
            "--include-review-required",
            action="store_true",
            help="Also process DiscoveredYoutubeVideo rows already marked review_required.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Classify promotable rows without writing catalog or quiz data.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 0)
        min_score = min(max(options["min_score"], 0), 100)
        dry_run = options["dry_run"]
        question_status = options["question_status"]
        include_review_required = options["include_review_required"]

        job = IngestionJob.objects.create(
            job_type="youtube_discovered_promotion",
            status=IngestionJob.Status.RUNNING,
            params={
                "limit": limit,
                "min_score": min_score,
                "quiz_pack_name": options["quiz_pack_name"],
                "private_pack": options["private_pack"],
                "question_status": question_status,
                "include_review_required": include_review_required,
                "dry_run": dry_run,
            },
            started_at=timezone.now(),
        )

        counters = {
            "processed": 0,
            "promoted": 0,
            "duplicate": 0,
            "review": 0,
            "failed": 0,
            "created_songs": 0,
            "created_sources": 0,
            "created_questions": 0,
            "pack_links": 0,
        }

        statuses = [DiscoveredYoutubeVideo.Status.DISCOVERED]
        if include_review_required:
            statuses.append(DiscoveredYoutubeVideo.Status.REVIEW_REQUIRED)

        candidates = DiscoveredYoutubeVideo.objects.filter(
            status__in=statuses,
            official_score__gte=min_score,
        ).order_by("-official_score", "artist_name", "song_title", "id")
        if limit:
            candidates = candidates[:limit]

        pack = None
        next_pack_order = 1
        if not dry_run:
            pack, _ = QuizPack.objects.get_or_create(
                name=options["quiz_pack_name"],
                defaults={
                    "description": "Automatically promoted from artist-first YouTube discovery.",
                    "is_public": not options["private_pack"],
                },
            )
            next_pack_order = _next_pack_order(pack)

        try:
            for candidate in candidates:
                counters["processed"] += 1
                try:
                    if dry_run:
                        result = _classify_candidate(candidate, min_score=min_score)
                    else:
                        with transaction.atomic():
                            locked_candidate = (
                                DiscoveredYoutubeVideo.objects.select_for_update().get(
                                    id=candidate.id
                                )
                            )
                            result = _promote_candidate(
                                locked_candidate,
                                job=job,
                                pack=pack,
                                next_pack_order=next_pack_order,
                                min_score=min_score,
                                question_status=question_status,
                            )
                            if result.pack_link_created:
                                next_pack_order += 1

                    counters[result.counter] += 1
                    counters["created_songs"] += int(result.song_created)
                    counters["created_sources"] += int(result.source_created)
                    counters["created_questions"] += int(result.question_created)
                    counters["pack_links"] += int(result.pack_link_created)

                    if result.counter == "review":
                        _log_review(job, candidate, result.reason, dry_run=dry_run)
                except Exception as exc:
                    counters["failed"] += 1
                    IngestionLog.objects.create(
                        job=job,
                        level=IngestionLog.Level.ERROR,
                        message="Failed to promote discovered YouTube video.",
                        context={
                            "discovered_youtube_video_id": candidate.id,
                            "video_id": candidate.video_id,
                            "title": candidate.song_title,
                            "artist": candidate.artist_name,
                            "error": str(exc),
                            "dry_run": dry_run,
                        },
                    )

            job.status = (
                IngestionJob.Status.FAILED
                if counters["processed"] and counters["failed"] == counters["processed"]
                else IngestionJob.Status.SUCCEEDED
            )
            job.total_count = counters["processed"]
            job.success_count = counters["promoted"] + counters["duplicate"]
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
        except Exception as exc:
            job.status = IngestionJob.Status.FAILED
            job.error_message = str(exc)
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error_message", "finished_at"])
            raise

        self.stdout.write(
            self.style.SUCCESS(
                "Processed {processed}, promoted {promoted}, duplicate {duplicate}, "
                "review {review}, failed {failed}, created_songs {created_songs}, "
                "created_sources {created_sources}, created_questions {created_questions}, "
                "pack_links {pack_links}.".format(**counters)
            )
        )


def _classify_candidate(
    candidate: DiscoveredYoutubeVideo,
    min_score: int,
) -> PromotionResult:
    review_reason = _candidate_review_reason(candidate, min_score=min_score)
    if review_reason:
        return PromotionResult(counter="review", reason=review_reason)
    return PromotionResult(counter="promoted")


def _promote_candidate(
    candidate: DiscoveredYoutubeVideo,
    job: IngestionJob,
    pack: QuizPack,
    next_pack_order: int,
    min_score: int,
    question_status: str,
) -> PromotionResult:
    review_reason = _candidate_review_reason(candidate, min_score=min_score)
    if review_reason:
        _mark_candidate_for_review(candidate, job, review_reason)
        return PromotionResult(counter="review", reason=review_reason)

    artist_name = _clean_display_value(candidate.artist_name)
    song_title = _clean_display_value(candidate.song_title)
    normalized_artist_name = normalize_answer(artist_name)
    normalized_song_title = normalize_answer(song_title)
    existing_source_review_reason = _existing_source_review_reason(
        candidate,
        normalized_artist_name=normalized_artist_name,
        normalized_song_title=normalized_song_title,
    )
    if existing_source_review_reason:
        _mark_candidate_for_review(candidate, job, existing_source_review_reason)
        return PromotionResult(counter="review", reason=existing_source_review_reason)

    artist, artist_created = _get_or_create_artist(
        name=artist_name,
        normalized_name=normalized_artist_name,
    )
    song, song_created = _get_or_create_song(
        title=song_title,
        normalized_title=normalized_song_title,
        artist=artist,
        candidate=candidate,
    )
    SongArtist.objects.get_or_create(
        song=song,
        artist=artist,
        role=SongArtist.Role.PRIMARY,
        defaults={"order": 0},
    )

    source, source_created, source_review_reason = _get_or_create_source(
        candidate=candidate,
        song=song,
    )
    if source_review_reason:
        _mark_candidate_for_review(candidate, job, source_review_reason)
        return PromotionResult(counter="review", reason=source_review_reason)

    question, question_created, question_review_reason = _get_or_create_question(
        candidate=candidate,
        song=song,
        source=source,
        question_status=question_status,
    )
    if question_review_reason:
        _mark_candidate_for_review(candidate, job, question_review_reason)
        return PromotionResult(counter="review", reason=question_review_reason)

    pack_link, pack_link_created = QuizPackQuestion.objects.get_or_create(
        pack=pack,
        question=question,
        defaults={"order": next_pack_order},
    )
    if not pack_link_created and pack_link.order <= 0:
        pack_link.order = next_pack_order
        pack_link.save(update_fields=["order"])

    _ensure_question_aliases(question, song_title=song_title, artist_name=artist_name)
    _mark_candidate_promoted(
        candidate,
        job=job,
        artist=artist,
        song=song,
        source=source,
        question=question,
        pack=pack,
    )

    return PromotionResult(
        counter="promoted" if song_created or source_created or question_created else "duplicate",
        song_created=song_created,
        source_created=source_created,
        question_created=question_created,
        pack_link_created=pack_link_created,
    )


def _candidate_review_reason(candidate: DiscoveredYoutubeVideo, min_score: int) -> str:
    if candidate.official_score < min_score:
        return "score_below_auto_promotion_threshold"
    if candidate.status == DiscoveredYoutubeVideo.Status.REVIEW_REQUIRED:
        return "already_marked_review_required"
    if not _clean_display_value(candidate.artist_name):
        return "missing_artist_name"
    if not _clean_display_value(candidate.song_title):
        return "missing_song_title"
    if not normalize_answer(candidate.artist_name):
        return "empty_normalized_artist_name"
    normalized_title = normalize_answer(candidate.song_title)
    if not normalized_title:
        return "empty_normalized_song_title"
    if normalized_title in TITLE_REVIEW_KEYS:
        return "ambiguous_song_title"
    if _source_type(candidate.source_type) is None:
        return "unknown_source_type"
    duration_seconds = _duration_seconds(candidate)
    if duration_seconds is not None and duration_seconds < MIN_PLAYABLE_DURATION_SECONDS:
        return "duration_too_short"
    if duration_seconds is not None and duration_seconds > MAX_PLAYABLE_DURATION_SECONDS:
        return "duration_too_long"
    return ""


def _get_or_create_artist(name: str, normalized_name: str) -> tuple[Artist, bool]:
    artist = Artist.objects.filter(normalized_name=normalized_name).order_by("id").first()
    if artist:
        return artist, False
    return (
        Artist.objects.create(
            name=name,
            normalized_name=normalized_name,
            artist_type=Artist.ArtistType.UNKNOWN,
        ),
        True,
    )


def _get_or_create_song(
    title: str,
    normalized_title: str,
    artist: Artist,
    candidate: DiscoveredYoutubeVideo,
) -> tuple[Song, bool]:
    song = (
        Song.objects.filter(
            normalized_title=normalized_title,
            primary_artist__normalized_name=artist.normalized_name,
        )
        .order_by("id")
        .first()
    )
    metadata_confidence = _metadata_confidence(candidate.official_score)
    if song:
        update_fields = []
        if not song.approved:
            song.approved = True
            update_fields.append("approved")
        if not song.playable:
            song.playable = True
            update_fields.append("playable")
        if song.metadata_confidence < metadata_confidence:
            song.metadata_confidence = metadata_confidence
            update_fields.append("metadata_confidence")
        if update_fields:
            update_fields.append("updated_at")
            song.save(update_fields=update_fields)
        return song, False

    duration_seconds = _duration_seconds(candidate)
    song = Song.objects.create(
        title=title,
        normalized_title=normalized_title,
        primary_artist=artist,
        duration_ms=duration_seconds * 1000 if duration_seconds else None,
        release_year=candidate.uploaded_year,
        metadata_confidence=metadata_confidence,
        approved=True,
        playable=True,
        raw_payload={
            "source": "youtube_artist_discovery",
            "discovered_youtube_video_id": candidate.id,
            "youtube_upload_year": candidate.uploaded_year,
            "youtube_upload_month": candidate.uploaded_month,
        },
    )
    return song, True


def _get_or_create_source(
    candidate: DiscoveredYoutubeVideo,
    song: Song,
) -> tuple[YoutubeSource, bool, str]:
    source_type = _source_type(candidate.source_type)
    if source_type is None:
        raise ValueError("candidate source_type was validated before source creation")

    published_at = _published_at(candidate)
    defaults = {
        "song": song,
        "title": candidate.youtube_title,
        "channel_title": candidate.channel_title,
        "channel_id": candidate.channel_id,
        "duration_seconds": _duration_seconds(candidate),
        "view_count": _view_count(candidate),
        "published_at": published_at,
        "source_type": source_type,
        "priority": SOURCE_TYPE_PRIORITIES.get(source_type, 100),
        "official_score": candidate.official_score,
        "status": YoutubeSource.Status.APPROVED,
        "raw_payload": _youtube_source_payload(candidate),
    }
    source, created = YoutubeSource.objects.get_or_create(
        video_id=candidate.video_id,
        defaults=defaults,
    )
    if created:
        return source, True, ""
    if source.song_id != song.id:
        return source, False, "youtube_video_already_matched_to_other_song"
    if source.status in {
        YoutubeSource.Status.REJECTED,
        YoutubeSource.Status.NEEDS_REVIEW,
        YoutubeSource.Status.BLOCKED,
        YoutubeSource.Status.UNAVAILABLE,
    }:
        return source, False, "existing_youtube_source_not_playable"
    _update_existing_source(source, defaults)
    return source, False, ""


def _update_existing_source(source: YoutubeSource, defaults: dict) -> None:
    update_fields = []
    for field in [
        "title",
        "channel_title",
        "channel_id",
        "duration_seconds",
        "view_count",
        "published_at",
        "source_type",
        "priority",
    ]:
        value = defaults[field]
        if value is not None and getattr(source, field) != value:
            setattr(source, field, value)
            update_fields.append(field)
    if source.official_score < defaults["official_score"]:
        source.official_score = defaults["official_score"]
        update_fields.append("official_score")
    if source.status != YoutubeSource.Status.APPROVED:
        source.status = YoutubeSource.Status.APPROVED
        update_fields.append("status")
    source.raw_payload = {
        **source.raw_payload,
        **defaults["raw_payload"],
    }
    update_fields.append("raw_payload")
    if update_fields:
        update_fields.append("updated_at")
        source.save(update_fields=sorted(set(update_fields)))


def _get_or_create_question(
    candidate: DiscoveredYoutubeVideo,
    song: Song,
    source: YoutubeSource,
    question_status: str,
) -> tuple[QuizQuestion, bool, str]:
    question, created = QuizQuestion.objects.get_or_create(
        song=song,
        youtube_source=source,
        defaults={
            "prompt_type": QuizQuestion.PromptType.AUDIO,
            "start_time_seconds": _start_time_seconds(_duration_seconds(candidate)),
            "play_duration_seconds": DEFAULT_PLAY_DURATION_SECONDS,
            "answer_title": song.title,
            "answer_artist": song.primary_artist.name,
            "difficulty": QuizQuestion.Difficulty.NORMAL,
            "status": question_status,
            "metadata": {
                "source": "youtube_artist_discovery",
                "discovered_youtube_video_id": candidate.id,
                "official_score": candidate.official_score,
            },
        },
    )
    if created:
        return question, True, ""
    if question.status == QuizQuestion.Status.DISABLED:
        return question, False, "existing_question_disabled"
    if (
        question.status == QuizQuestion.Status.NEEDS_REVIEW
        and question_status == QuizQuestion.Status.APPROVED
    ):
        return question, False, "existing_question_needs_review"

    update_fields = []
    if question.status != question_status:
        question.status = question_status
        update_fields.append("status")
    if question.answer_title != song.title:
        question.answer_title = song.title
        update_fields.append("answer_title")
    if question.answer_artist != song.primary_artist.name:
        question.answer_artist = song.primary_artist.name
        update_fields.append("answer_artist")
    if update_fields:
        update_fields.append("updated_at")
        question.save(update_fields=update_fields)
    return question, False, ""


def _existing_source_review_reason(
    candidate: DiscoveredYoutubeVideo,
    normalized_artist_name: str,
    normalized_song_title: str,
) -> str:
    source = (
        YoutubeSource.objects.filter(video_id=candidate.video_id)
        .select_related("song__primary_artist")
        .first()
    )
    if not source:
        return ""
    if source.status in {
        YoutubeSource.Status.REJECTED,
        YoutubeSource.Status.NEEDS_REVIEW,
        YoutubeSource.Status.BLOCKED,
        YoutubeSource.Status.UNAVAILABLE,
    }:
        return "existing_youtube_source_not_playable"
    if (
        source.song.normalized_title != normalized_song_title
        or source.song.primary_artist.normalized_name != normalized_artist_name
    ):
        return "youtube_video_already_matched_to_other_song"
    return ""


def _ensure_question_aliases(
    question: QuizQuestion,
    song_title: str,
    artist_name: str,
) -> None:
    for title_alias in _title_aliases(song_title):
        _create_alias(
            question=question,
            answer_type=QuizAnswerAlias.AnswerType.TITLE,
            value=title_alias,
        )
    for artist_alias in _artist_aliases(artist_name):
        _create_alias(
            question=question,
            answer_type=QuizAnswerAlias.AnswerType.ARTIST,
            value=artist_alias,
        )


def _create_alias(question: QuizQuestion, answer_type: str, value: str) -> None:
    value = _clean_display_value(value)
    normalized_value = normalize_answer(value)
    if not value or not normalized_value:
        return
    QuizAnswerAlias.objects.get_or_create(
        question=question,
        answer_type=answer_type,
        normalized_value=normalized_value,
        defaults={"value": value},
    )


def _mark_candidate_promoted(
    candidate: DiscoveredYoutubeVideo,
    job: IngestionJob,
    artist: Artist,
    song: Song,
    source: YoutubeSource,
    question: QuizQuestion,
    pack: QuizPack,
) -> None:
    candidate.status = DiscoveredYoutubeVideo.Status.PROMOTED
    candidate.raw_payload = {
        **candidate.raw_payload,
        "auto_promotion": {
            "job_id": job.id,
            "promoted_at": timezone.now().isoformat(),
            "artist_id": artist.id,
            "song_id": song.id,
            "youtube_source_id": source.id,
            "quiz_question_id": question.id,
            "quiz_pack_id": pack.id,
        },
    }
    candidate.save(update_fields=["status", "raw_payload", "updated_at"])


def _mark_candidate_for_review(
    candidate: DiscoveredYoutubeVideo,
    job: IngestionJob,
    reason: str,
) -> None:
    candidate.status = DiscoveredYoutubeVideo.Status.REVIEW_REQUIRED
    candidate.raw_payload = {
        **candidate.raw_payload,
        "auto_promotion_review": {
            "job_id": job.id,
            "reviewed_at": timezone.now().isoformat(),
            "reason": reason,
        },
    }
    candidate.save(update_fields=["status", "raw_payload", "updated_at"])


def _log_review(
    job: IngestionJob,
    candidate: DiscoveredYoutubeVideo,
    reason: str,
    dry_run: bool,
) -> None:
    IngestionLog.objects.create(
        job=job,
        level=IngestionLog.Level.INFO,
        message="Discovered YouTube video left for review.",
        context={
            "discovered_youtube_video_id": candidate.id,
            "video_id": candidate.video_id,
            "title": candidate.song_title,
            "artist": candidate.artist_name,
            "official_score": candidate.official_score,
            "reason": reason,
            "dry_run": dry_run,
        },
    )


def _next_pack_order(pack: QuizPack) -> int:
    max_order = pack.pack_questions.aggregate(max_order=Max("order"))["max_order"]
    return (max_order or 0) + 1


def _clean_display_value(value: str) -> str:
    return " ".join((value or "").strip().split())[:255]


def _duration_seconds(candidate: DiscoveredYoutubeVideo) -> int | None:
    return _parse_int(candidate.raw_payload.get("duration_seconds"))


def _view_count(candidate: DiscoveredYoutubeVideo) -> int | None:
    return _parse_int(candidate.raw_payload.get("view_count"))


def _parse_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _published_at(candidate: DiscoveredYoutubeVideo):
    published_at = candidate.raw_payload.get("published_at")
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def _source_type(value: str) -> str | None:
    valid_source_types = {choice[0] for choice in YoutubeSource.SourceType.choices}
    return value if value in valid_source_types else None


def _metadata_confidence(official_score: int) -> int:
    if official_score >= 90:
        return 90
    if official_score >= 80:
        return 80
    return 70


def _start_time_seconds(duration_seconds: int | None) -> int:
    if not duration_seconds:
        return 0
    latest_start = max(duration_seconds - DEFAULT_PLAY_DURATION_SECONDS - 5, 0)
    if duration_seconds >= 120:
        return min(60, latest_start)
    if duration_seconds >= 80:
        return min(40, latest_start)
    return min(20, latest_start)


def _youtube_source_payload(candidate: DiscoveredYoutubeVideo) -> dict:
    return {
        "source": "youtube_artist_discovery",
        "discovered_youtube_video_id": candidate.id,
        "discovery_reason": candidate.raw_payload.get("reason", ""),
        "discovery_query": candidate.raw_payload.get("discovery_query", ""),
    }


def _title_aliases(title: str) -> tuple[str, ...]:
    aliases = [title]
    without_brackets = re.sub(r"\s*[\[(][^\])]*[\])]\s*", " ", title)
    aliases.append(without_brackets)
    return _unique_clean_values(aliases)


def _artist_aliases(artist: str) -> tuple[str, ...]:
    aliases = [artist]
    aliases.extend(re.findall(r"\(([^)]*)\)|\[([^\]]*)\]", artist))
    aliases.extend(re.split(r"\s*[()/,&]\s*", artist))
    flattened = []
    for alias in aliases:
        if isinstance(alias, tuple):
            flattened.extend(part for part in alias if part)
        else:
            flattened.append(alias)
    return _unique_clean_values(flattened)


def _unique_clean_values(values) -> tuple[str, ...]:
    seen = set()
    result = []
    for value in values:
        cleaned = _clean_display_value(value)
        normalized = normalize_answer(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)
    return tuple(result)
