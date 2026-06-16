from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Artist, Song, YoutubeSource
from apps.ingestion.models import IngestionJob, IngestionLog, RawCandidate
from apps.ingestion.youtube_matching import (
    build_youtube_source_defaults,
    find_youtube_match,
)


class Command(BaseCommand):
    help = "Match raw candidates to official YouTube videos and promote clear matches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of raw candidates to process.",
        )
        parser.add_argument(
            "--max-results",
            type=int,
            default=8,
            help="Maximum YouTube search results to inspect per candidate.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Classify candidates without writing Song/YoutubeSource/status changes.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        max_results = max(options["max_results"], 1)
        dry_run = options["dry_run"]

        job = IngestionJob.objects.create(
            job_type="youtube_match",
            status=IngestionJob.Status.RUNNING,
            params={
                "limit": limit,
                "max_results": max_results,
                "dry_run": dry_run,
            },
            started_at=timezone.now(),
        )

        counters = {
            "processed": 0,
            "approved": 0,
            "duplicate": 0,
            "review": 0,
            "rejected": 0,
            "failed": 0,
        }

        candidates = RawCandidate.objects.filter(
            source_type=RawCandidate.SourceType.B,
            status=RawCandidate.Status.PENDING,
        ).order_by(
            "first_observed_year",
            "first_observed_month",
            "first_observed_sample_day",
            "id",
        )[:limit]

        try:
            for candidate in candidates:
                counters["processed"] += 1
                try:
                    decision = find_youtube_match(
                        title=candidate.raw_title,
                        artist=candidate.raw_artist,
                        max_results=max_results,
                    )
                    if dry_run:
                        _log_decision(job, candidate, decision, dry_run=True)
                        counters[_counter_key(decision.action)] += 1
                        continue

                    with transaction.atomic():
                        candidate = RawCandidate.objects.select_for_update().get(id=candidate.id)
                        result = apply_decision(candidate, decision)
                    counters[result] += 1
                    _log_decision(job, candidate, decision, result=result)
                except Exception as exc:
                    counters["failed"] += 1
                    IngestionLog.objects.create(
                        job=job,
                        level=IngestionLog.Level.ERROR,
                        message="Failed to match raw candidate.",
                        context={
                            "raw_candidate_id": candidate.id,
                            "title": candidate.raw_title,
                            "artist": candidate.raw_artist,
                            "error": str(exc),
                        },
                    )

            job.status = (
                IngestionJob.Status.FAILED
                if counters["processed"] and counters["failed"] == counters["processed"]
                else IngestionJob.Status.SUCCEEDED
            )
            job.total_count = counters["processed"]
            job.success_count = counters["approved"] + counters["duplicate"]
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
                "Processed {processed}, approved {approved}, duplicate {duplicate}, "
                "review {review}, rejected {rejected}, failed {failed}.".format(**counters)
            )
        )


def apply_decision(candidate: RawCandidate, decision):
    if decision.action == "approve":
        song, song_created = _get_or_create_song(candidate)
        if decision.video is None:
            raise ValueError("Approved decision did not include a video.")

        source_defaults = build_youtube_source_defaults(decision)
        source, created = YoutubeSource.objects.get_or_create(
            video_id=decision.video.video_id,
            defaults={
                "song": song,
                **source_defaults,
            },
        )
        if not created and source.song_id != song.id:
            candidate.status = RawCandidate.Status.REVIEW_REQUIRED
            candidate.reject_reason = "youtube_video_already_matched_to_other_song"
            candidate.metadata_payload = _review_payload(decision)
            candidate.save(
                update_fields=["status", "reject_reason", "metadata_payload", "updated_at"]
            )
            return "review"

        song.approved = True
        song.playable = True
        song.save(update_fields=["approved", "playable", "updated_at"])

        candidate.matched_song = song
        candidate.status = (
            RawCandidate.Status.PROMOTED if song_created else RawCandidate.Status.DUPLICATE
        )
        candidate.reject_reason = ""
        candidate.metadata_payload = {
            "youtube_match": {
                "video_id": decision.video.video_id,
                "title": decision.video.title,
                "channel_title": decision.video.channel_title,
                "official_score": decision.official_score,
                "reason": decision.reason,
            }
        }
        candidate.save(
            update_fields=[
                "matched_song",
                "status",
                "reject_reason",
                "metadata_payload",
                "updated_at",
            ]
        )
        return "approved" if song_created else "duplicate"

    if decision.action == "review":
        candidate.status = RawCandidate.Status.REVIEW_REQUIRED
        candidate.reject_reason = decision.reason
        candidate.metadata_payload = _review_payload(decision)
        candidate.save(update_fields=["status", "reject_reason", "metadata_payload", "updated_at"])
        return "review"

    candidate.status = RawCandidate.Status.REJECTED
    candidate.reject_reason = decision.reason
    candidate.metadata_payload = {}
    candidate.save(update_fields=["status", "reject_reason", "metadata_payload", "updated_at"])
    return "rejected"


def _get_or_create_song(candidate: RawCandidate) -> tuple[Song, bool]:
    existing_song = Song.objects.filter(
        normalized_title=candidate.raw_title_key,
        primary_artist__normalized_name=candidate.raw_artist_key,
    ).first()
    if existing_song:
        return existing_song, False

    artist, _ = Artist.objects.get_or_create(
        normalized_name=candidate.raw_artist_key,
        defaults={
            "name": candidate.raw_artist,
            "artist_type": Artist.ArtistType.UNKNOWN,
        },
    )
    song = Song.objects.create(
        title=candidate.raw_title,
        normalized_title=candidate.raw_title_key,
        primary_artist=artist,
        metadata_confidence=60,
        approved=True,
        playable=True,
    )
    return song, True


def _review_payload(decision) -> dict:
    return {
        "youtube_review_candidates": list(decision.review_candidates),
        "official_score": decision.official_score,
        "reason": decision.reason,
    }


def _counter_key(action: str) -> str:
    if action == "approve":
        return "approved"
    if action == "review":
        return "review"
    return "rejected"


def _log_decision(job: IngestionJob, candidate: RawCandidate, decision, **extra) -> None:
    video = decision.video
    IngestionLog.objects.create(
        job=job,
        level=IngestionLog.Level.INFO,
        message="Matched YouTube candidate.",
        context={
            "raw_candidate_id": candidate.id,
            "title": candidate.raw_title,
            "artist": candidate.raw_artist,
            "action": decision.action,
            "official_score": decision.official_score,
            "reason": decision.reason,
            "video_id": video.video_id if video else None,
            "video_title": video.title if video else None,
            "channel_title": video.channel_title if video else None,
            **extra,
        },
    )
