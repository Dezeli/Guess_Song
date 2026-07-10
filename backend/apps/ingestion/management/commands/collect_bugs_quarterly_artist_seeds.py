import time
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ingestion.management.commands.collect_bugs_chart_samples import (
    CHART_TARGETS,
    TRACK_ROW_RE,
    _extract_title,
    _fetch_html,
    _response_matches_sample_date,
    extract_artist_names,
    normalize_raw_key,
)
from apps.ingestion.models import ArtistSeed, IngestionJob, IngestionLog

SOURCE_TYPE = ArtistSeed.SourceType.B
DEFAULT_START_YEAR = 2007
DEFAULT_RANK_LIMIT = 100
QUARTER_SAMPLE_DATES = ((3, 15), (6, 15), (9, 15), (12, 15))


class Command(BaseCommand):
    help = "Collect artist seeds from quarterly representative Bugs weekly chart pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-year",
            type=int,
            default=DEFAULT_START_YEAR,
            help="First year to sample.",
        )
        parser.add_argument(
            "--end-year",
            type=int,
            default=None,
            help="Last year to sample. Defaults to the current year.",
        )
        parser.add_argument(
            "--rank-limit",
            type=int,
            default=DEFAULT_RANK_LIMIT,
            help="Maximum chart rank to parse per sampled weekly chart page.",
        )
        parser.add_argument(
            "--chart",
            default="total",
            help="Chart key to sample. Defaults to total weekly chart.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.5,
            help="Delay in seconds between Bugs requests.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Maximum pages to request. Useful for one-page test runs.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and parse without writing ArtistSeed rows.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        start_year = options["start_year"]
        end_year = options["end_year"] or today.year
        rank_limit = max(options["rank_limit"], 1)
        delay = max(options["delay"], 0)
        max_pages = options["max_pages"]
        dry_run = options["dry_run"]
        chart = _get_chart(options["chart"])
        sample_dates = _quarterly_sample_dates(start_year, end_year, today)

        job = IngestionJob.objects.create(
            job_type="bugs_quarterly_artist_seed",
            status=IngestionJob.Status.RUNNING,
            params={
                "source_type": SOURCE_TYPE,
                "chart": chart.key,
                "start_year": start_year,
                "end_year": end_year,
                "rank_limit": rank_limit,
                "sample_dates": [sample.strftime("%Y%m%d") for sample in sample_dates],
                "max_pages": max_pages,
                "dry_run": dry_run,
            },
            started_at=timezone.now(),
        )

        counters = defaultdict(int)
        requested_pages = 0

        try:
            for sample in sample_dates:
                if max_pages is not None and requested_pages >= max_pages:
                    break
                requested_pages += 1

                parsed, observations, skipped, failed = collect_quarterly_page(
                    chart=chart,
                    sample_date=sample,
                    rank_limit=rank_limit,
                    job=job,
                )
                counters["parsed"] += parsed
                counters["skipped"] += skipped
                counters["failed"] += failed

                if observations:
                    if dry_run:
                        created = 0
                        updated = 0
                    else:
                        created, updated = save_quarterly_artist_observations(
                            observations=observations,
                            sample_date=sample,
                            job=job,
                        )
                    counters["created"] += created
                    counters["updated"] += updated

                if delay:
                    time.sleep(delay)

            job.status = (
                IngestionJob.Status.FAILED
                if requested_pages and counters["failed"] == requested_pages
                else IngestionJob.Status.SUCCEEDED
            )
            job.total_count = counters["parsed"]
            job.success_count = counters["created"]
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
                "Collected "
                f"{counters['parsed']} parsed artist rows, "
                f"{counters['created']} new seeds, "
                f"{counters['updated']} updated seeds, "
                f"{counters['skipped']} skipped pages, "
                f"{counters['failed']} failed pages."
            )
        )


def collect_quarterly_page(chart, sample_date: date, rank_limit: int, job: IngestionJob):
    page_url = chart.build_url(sample_date.strftime("%Y%m%d"))
    try:
        html = _fetch_html(page_url)
        if not _response_matches_sample_date(html, sample_date):
            _log(
                job,
                IngestionLog.Level.WARNING,
                "Skipped fallback or mismatched quarterly Bugs chart page.",
                {"sample_date": sample_date.isoformat(), "chart": chart.key},
            )
            return 0, {}, 1, 0

        observations = {}
        parsed = 0
        for rank, title, artist in parse_ranked_artist_occurrences(html, rank_limit=rank_limit):
            artist_key = normalize_raw_key(artist)
            title_key = normalize_raw_key(title)
            if not artist_key or not title_key:
                continue

            parsed += 1
            observation_key = (artist_key, title_key)
            weight = _rank_weight(rank)
            existing = observations.get(observation_key)
            if existing is None or weight > existing["weight"]:
                observations[observation_key] = {
                    "artist": artist,
                    "rank": rank,
                    "weight": weight,
                }

        _log(
            job,
            IngestionLog.Level.INFO,
            "Collected quarterly Bugs artist seed page.",
            {
                "sample_date": sample_date.isoformat(),
                "chart": chart.key,
                "rank_limit": rank_limit,
                "parsed": parsed,
                "artist_title_pairs": len(observations),
            },
        )
        return parsed, observations, 0, 0
    except Exception as exc:
        _log(
            job,
            IngestionLog.Level.ERROR,
            "Failed to collect quarterly Bugs artist seed page.",
            {"sample_date": sample_date.isoformat(), "chart": chart.key, "error": str(exc)},
        )
        return 0, {}, 0, 1


def parse_ranked_artist_occurrences(
    html: str,
    rank_limit: int,
) -> list[tuple[int, str, str]]:
    occurrences = []
    for rank, row_match in enumerate(TRACK_ROW_RE.finditer(html), start=1):
        if rank > rank_limit:
            break

        row_html = row_match.group("body")
        title = _extract_title(row_html)
        if not title:
            continue

        for artist in extract_artist_names(row_html):
            artist_key = normalize_raw_key(artist)
            if not artist_key or _is_ignored_artist_key(artist_key):
                continue
            occurrences.append((rank, title, artist))

    return occurrences


def save_quarterly_artist_observations(
    observations: dict,
    sample_date: date,
    job: IngestionJob,
) -> tuple[int, int]:
    created_count = 0
    updated_count = 0

    merged = defaultdict(lambda: {"artist": "", "item_count": 0, "weighted_score": 0})
    for (artist_key, _title_key), observation in observations.items():
        current = merged[artist_key]
        current["artist"] = observation["artist"]
        current["item_count"] += 1
        current["weighted_score"] += observation["weight"]

    for artist_key, payload in merged.items():
        artist = payload["artist"]
        item_count = payload["item_count"]
        weighted_score = payload["weighted_score"]
        sample_key = sample_date.strftime("%Y%m%d")

        with transaction.atomic():
            try:
                seed, created = ArtistSeed.objects.select_for_update().get_or_create(
                    source_type=SOURCE_TYPE,
                    raw_artist_key=artist_key,
                    defaults={
                        "job": job,
                        "raw_artist": artist,
                        "display_artist": artist,
                        "first_observed_year": sample_date.year,
                        "first_observed_month": sample_date.month,
                        "first_observed_sample_day": sample_date.day,
                        "last_observed_year": sample_date.year,
                        "last_observed_month": sample_date.month,
                        "last_observed_sample_day": sample_date.day,
                        "observed_count": item_count,
                        "observed_sample_count": 1,
                        "observed_weight_score": weighted_score,
                        "metadata_payload": {
                            "observed_samples": {
                                sample_key: {
                                    "item_count": item_count,
                                    "weighted_score": weighted_score,
                                }
                            }
                        },
                    },
                )
            except IntegrityError:
                created = False
                seed = ArtistSeed.objects.select_for_update().get(
                    source_type=SOURCE_TYPE,
                    raw_artist_key=artist_key,
                )

            if created:
                created_count += 1
                continue

            observed_samples = seed.metadata_payload.get("observed_samples", {})
            if sample_key in observed_samples:
                continue

            observed_samples[sample_key] = {
                "item_count": item_count,
                "weighted_score": weighted_score,
            }
            seed.observed_count += item_count
            seed.observed_sample_count = len(observed_samples)
            seed.observed_weight_score += weighted_score
            seed.metadata_payload = {"observed_samples": observed_samples}

            if _is_earlier_observation(seed, sample_date):
                seed.first_observed_year = sample_date.year
                seed.first_observed_month = sample_date.month
                seed.first_observed_sample_day = sample_date.day
            if _is_later_observation(seed, sample_date):
                seed.last_observed_year = sample_date.year
                seed.last_observed_month = sample_date.month
                seed.last_observed_sample_day = sample_date.day
                seed.display_artist = artist

            seed.save(
                update_fields=[
                    "display_artist",
                    "first_observed_year",
                    "first_observed_month",
                    "first_observed_sample_day",
                    "last_observed_year",
                    "last_observed_month",
                    "last_observed_sample_day",
                    "observed_count",
                    "observed_sample_count",
                    "observed_weight_score",
                    "metadata_payload",
                    "updated_at",
                ]
            )
            updated_count += 1

    return created_count, updated_count


def _quarterly_sample_dates(start_year: int, end_year: int, today: date) -> list[date]:
    sample_dates = []
    for year in range(start_year, end_year + 1):
        for month, day in QUARTER_SAMPLE_DATES:
            sample = date(year, month, day)
            if sample <= today:
                sample_dates.append(sample)
    return sample_dates


def _get_chart(chart_key: str):
    for chart in CHART_TARGETS:
        if chart.key == chart_key:
            return chart
    raise ValueError(f"Unknown Bugs chart key: {chart_key}")


def _rank_weight(rank: int) -> int:
    if rank <= 10:
        return 5
    if rank <= 30:
        return 3
    return 1


def _is_earlier_observation(seed: ArtistSeed, sample_date: date) -> bool:
    current = (
        seed.first_observed_year or 9999,
        seed.first_observed_month or 99,
        seed.first_observed_sample_day or 99,
    )
    incoming = (sample_date.year, sample_date.month, sample_date.day)
    return incoming < current


def _is_later_observation(seed: ArtistSeed, sample_date: date) -> bool:
    current = (
        seed.last_observed_year or 0,
        seed.last_observed_month or 0,
        seed.last_observed_sample_day or 0,
    )
    incoming = (sample_date.year, sample_date.month, sample_date.day)
    return incoming > current


def _is_ignored_artist_key(key: str) -> bool:
    return key in {"various artists", "various artist", "original soundtrack", "unknown"}


def _log(job: IngestionJob, level: str, message: str, context: dict) -> None:
    IngestionLog.objects.create(
        job=job,
        level=level,
        message=message,
        context=context,
    )
