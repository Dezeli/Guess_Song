from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import YoutubeSource
from apps.ingestion.models import IngestionJob, IngestionLog
from apps.ingestion.youtube_matching import YouTubeQuotaExhausted, _youtube_get
from apps.quizzes.models import QuizQuestion


BATCH_SIZE = 50


class Command(BaseCommand):
    help = "Check approved YouTube sources for embeddability and remove blocked embeds from play."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum approved sources to check. 0 means all approved sources.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Check YouTube API responses without changing source or question status.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 0)
        dry_run = options["dry_run"]
        job = IngestionJob.objects.create(
            job_type="youtube_source_embeddability_check",
            status=IngestionJob.Status.RUNNING,
            params={"limit": limit, "dry_run": dry_run},
            started_at=timezone.now(),
        )
        counters = {
            "checked": 0,
            "embeddable": 0,
            "not_embeddable": 0,
            "missing": 0,
            "questions_returned": 0,
            "failed": 0,
        }

        source_queryset = (
            YoutubeSource.objects.filter(status=YoutubeSource.Status.APPROVED)
            .order_by("id")
            .values("id", "video_id")
        )
        if limit:
            source_queryset = source_queryset[:limit]
        sources = list(source_queryset)

        try:
            for batch in _chunks(sources, BATCH_SIZE):
                try:
                    statuses = _fetch_embeddability([item["video_id"] for item in batch])
                except YouTubeQuotaExhausted:
                    raise
                except Exception as exc:
                    counters["failed"] += len(batch)
                    IngestionLog.objects.create(
                        job=job,
                        level=IngestionLog.Level.ERROR,
                        message="Failed to check YouTube source embeddability batch.",
                        context={"error": str(exc), "source_ids": [item["id"] for item in batch]},
                    )
                    continue

                for item in batch:
                    counters["checked"] += 1
                    embeddable = statuses.get(item["video_id"])
                    if embeddable is None:
                        counters["missing"] += 1
                        returned = _mark_source_unavailable(
                            source_id=item["id"],
                            reason="youtube_video_missing",
                            embeddable=None,
                            dry_run=dry_run,
                        )
                        counters["questions_returned"] += returned
                    elif embeddable is False:
                        counters["not_embeddable"] += 1
                        returned = _mark_source_unavailable(
                            source_id=item["id"],
                            reason="youtube_video_not_embeddable",
                            embeddable=False,
                            dry_run=dry_run,
                        )
                        counters["questions_returned"] += returned
                    else:
                        counters["embeddable"] += 1
                        if not dry_run:
                            YoutubeSource.objects.filter(id=item["id"]).update(
                                raw_payload=_payload_with_embeddability(item["id"], True),
                                last_checked_at=timezone.now(),
                                updated_at=timezone.now(),
                            )

            job.status = IngestionJob.Status.SUCCEEDED
            job.total_count = counters["checked"]
            job.success_count = counters["embeddable"]
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
                "Checked {checked}, embeddable {embeddable}, not_embeddable {not_embeddable}, "
                "missing {missing}, questions_returned {questions_returned}, failed {failed}.".format(
                    **counters
                )
            )
        )


def _chunks(items: list[dict], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _fetch_embeddability(video_ids: list[str]) -> dict[str, bool]:
    payload = _youtube_get(
        "/videos",
        {
            "part": "status",
            "id": ",".join(video_ids),
        },
    )
    return {
        item["id"]: item.get("status", {}).get("embeddable")
        for item in payload.get("items", [])
    }


def _payload_with_embeddability(source_id: int, embeddable: bool | None) -> dict:
    source = YoutubeSource.objects.only("raw_payload").get(id=source_id)
    return {
        **source.raw_payload,
        "embeddable": embeddable,
        "embeddability_checked_at": timezone.now().isoformat(),
    }


def _mark_source_unavailable(
    *,
    source_id: int,
    reason: str,
    embeddable: bool | None,
    dry_run: bool,
) -> int:
    if dry_run:
        return QuizQuestion.objects.filter(
            youtube_source_id=source_id,
            status=QuizQuestion.Status.APPROVED,
        ).count()

    with transaction.atomic():
        source = YoutubeSource.objects.select_for_update().get(id=source_id)
        source.status = YoutubeSource.Status.UNAVAILABLE
        source.reject_reason = reason
        source.raw_payload = {
            **source.raw_payload,
            "embeddable": embeddable,
            "embeddability_checked_at": timezone.now().isoformat(),
        }
        source.last_checked_at = timezone.now()
        source.save(
            update_fields=[
                "status",
                "reject_reason",
                "raw_payload",
                "last_checked_at",
                "updated_at",
            ]
        )
        return QuizQuestion.objects.filter(
            youtube_source=source,
            status=QuizQuestion.Status.APPROVED,
        ).update(
            status=QuizQuestion.Status.NEEDS_REVIEW,
            updated_at=timezone.now(),
        )
