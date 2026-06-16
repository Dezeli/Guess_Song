import time
from collections import defaultdict
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ingestion.management.commands.collect_bugs_chart_samples import (
    CHART_TARGETS,
    DEFAULT_DATES,
    _fetch_html,
    _response_matches_sample_date,
    normalize_raw_key,
    parse_chart_artist_occurrences,
)
from apps.ingestion.models import ArtistSeed, IngestionJob, IngestionLog

SOURCE_TYPE = ArtistSeed.SourceType.B


class Command(BaseCommand):
    help = "Collect artist seeds from sampled public chart pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dates",
            nargs="+",
            default=DEFAULT_DATES,
            help="Sample dates in YYYYMMDD format. Defaults to 20260601 and 20200115.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.5,
            help="Delay in seconds between requests.",
        )
        parser.add_argument(
            "--backfill",
            action="store_true",
            help="Walk backward from the start month until every selected chart has no older data.",
        )
        parser.add_argument(
            "--start-month",
            default=None,
            help="Backfill start month in YYYY-MM format. Defaults to the current month.",
        )
        parser.add_argument(
            "--groups",
            nargs="+",
            default=None,
            help="Chart groups to include: total domestic overseas etc.",
        )
        parser.add_argument(
            "--charts",
            nargs="+",
            default=None,
            help="Chart keys to include, such as total k_ballad k_dance ost.",
        )
        parser.add_argument(
            "--exclude-groups",
            nargs="+",
            default=[],
            help="Chart groups to exclude.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Maximum chart pages to request in this run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and parse without writing ArtistSeed rows.",
        )

    def handle(self, *args, **options):
        charts = _filter_charts(options["groups"], options["exclude_groups"], options["charts"])
        sample_dates = [_parse_sample_date(raw) for raw in options["dates"]]
        delay = max(options["delay"], 0)
        dry_run = options["dry_run"]
        max_pages = options["max_pages"]

        job = IngestionJob.objects.create(
            job_type="artist_seed_sample",
            status=IngestionJob.Status.RUNNING,
            params={
                "source_type": SOURCE_TYPE,
                "sample_dates": [sample.strftime("%Y%m%d") for sample in sample_dates],
                "chart_count": len(charts),
                "chart_keys": [chart.key for chart in charts],
                "chart_groups": sorted({chart.group for chart in charts}),
                "excluded_groups": options["exclude_groups"],
                "backfill": options["backfill"],
                "delay": delay,
                "max_pages": max_pages,
                "dry_run": dry_run,
            },
            started_at=timezone.now(),
        )

        parsed_artists = 0
        created_artists = 0
        updated_artists = 0
        skipped_pages = 0
        failed_pages = 0

        try:
            if options["backfill"]:
                results = collect_backfill(
                    charts=charts,
                    job=job,
                    dry_run=dry_run,
                    delay=delay,
                    start_month=options["start_month"],
                    max_pages=max_pages,
                )
            else:
                results = collect_samples(
                    charts=charts,
                    sample_dates=sample_dates,
                    job=job,
                    dry_run=dry_run,
                    delay=delay,
                    max_pages=max_pages,
                )
            parsed_artists = results["parsed"]
            created_artists = results["created"]
            updated_artists = results["updated"]
            skipped_pages = results["skipped"]
            failed_pages = results["failed"]

            job.status = (
                IngestionJob.Status.FAILED
                if failed_pages == len(CHART_TARGETS) * len(sample_dates)
                else IngestionJob.Status.SUCCEEDED
            )
            job.total_count = parsed_artists
            job.success_count = created_artists
            job.fail_count = failed_pages
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
                f"{parsed_artists} parsed artists, "
                f"{created_artists} new seeds, "
                f"{updated_artists} updated seeds, "
                f"{skipped_pages} skipped pages, "
                f"{failed_pages} failed pages."
            )
        )


def collect_samples(
    charts,
    sample_dates: list[date],
    job: IngestionJob,
    dry_run: bool,
    delay: float,
    max_pages: int | None,
) -> dict[str, int]:
    results = defaultdict(int)
    requested_pages = 0

    for sample in sample_dates:
            song_observations = {}
            for chart in charts:
                if max_pages is not None and requested_pages >= max_pages:
                    break
                requested_pages += 1
                parsed, observations, skipped, failed = collect_chart_page(chart, sample, job)
                results["parsed"] += parsed
                results["skipped"] += skipped
                results["failed"] += failed
                _merge_song_observations(song_observations, observations)
                if delay:
                    time.sleep(delay)
            if song_observations:
                if dry_run:
                    created = 0
                    updated = 0
                else:
                    created, updated = save_artist_seed_observations(
                        song_observations=song_observations,
                        sample_date=sample,
                        job=job,
                    )
                results["created"] += created
                results["updated"] += updated
            if max_pages is not None and requested_pages >= max_pages:
                break

    return results


def collect_backfill(
    charts,
    job: IngestionJob,
    dry_run: bool,
    delay: float,
    start_month: str | None,
    max_pages: int | None,
) -> dict[str, int]:
    results = defaultdict(int)
    today = timezone.localdate()
    year, month = _parse_start_month(start_month, today)
    active_charts = {chart.key: chart for chart in charts}
    requested_pages = 0

    while active_charts:
        month_dates = _sample_dates_for_month(year, month, today)
        if not month_dates:
            year, month = _previous_month(year, month)
            continue

        month_misses = {chart_key: 0 for chart_key in active_charts}
        for sample in month_dates:
            song_observations = {}
            for chart_key, chart in list(active_charts.items()):
                if max_pages is not None and requested_pages >= max_pages:
                    return results
                requested_pages += 1
                parsed, observations, skipped, failed = collect_chart_page(chart, sample, job)
                results["parsed"] += parsed
                results["skipped"] += skipped
                results["failed"] += failed
                if skipped:
                    month_misses[chart_key] += 1
                _merge_song_observations(song_observations, observations)
                if delay:
                    time.sleep(delay)
            if song_observations:
                if dry_run:
                    created = 0
                    updated = 0
                else:
                    created, updated = save_artist_seed_observations(
                        song_observations=song_observations,
                        sample_date=sample,
                        job=job,
                    )
                results["created"] += created
                results["updated"] += updated

        for chart_key, miss_count in month_misses.items():
            if miss_count >= len(month_dates):
                active_charts.pop(chart_key, None)

        year, month = _previous_month(year, month)

    return results


def collect_chart_page(chart, sample_date: date, job: IngestionJob):
    page_url = chart.build_url(sample_date.strftime("%Y%m%d"))
    try:
        html = _fetch_html(page_url)
        if not _response_matches_sample_date(html, sample_date):
            _log(
                job,
                IngestionLog.Level.WARNING,
                "Skipped fallback or mismatched chart page.",
                {"sample_date": sample_date.isoformat(), "group": chart.group},
            )
            return 0, {}, 1, 0

        artists = parse_chart_artist_occurrences(html, row_limit=chart.row_limit)
        observations = {}
        for title, artist in artists:
            artist_key = normalize_raw_key(artist)
            title_key = normalize_raw_key(title)
            if not artist_key or not title_key:
                continue
            observation_key = (artist_key, title_key)
            existing = observations.get(observation_key)
            if existing is None or chart.weight > existing["weight"]:
                observations[observation_key] = {
                    "artist": artist,
                    "weight": chart.weight,
                }

        _log(
            job,
            IngestionLog.Level.INFO,
            "Collected artist seed sample.",
            {
                "sample_date": sample_date.isoformat(),
                "group": chart.group,
                "parsed": len(artists),
                "row_limit": chart.row_limit,
                "weight": chart.weight,
            },
        )
        return len(artists), observations, 0, 0
    except Exception as exc:
        _log(
            job,
            IngestionLog.Level.ERROR,
            "Failed to collect artist seed sample.",
            {"sample_date": sample_date.isoformat(), "group": chart.group, "error": str(exc)},
        )
        return 0, {}, 0, 1


def _merge_song_observations(target: dict, incoming: dict) -> None:
    for key, observation in incoming.items():
        existing = target.get(key)
        if existing is None or observation["weight"] > existing["weight"]:
            target[key] = observation


def save_artist_seed_observations(
    song_observations: dict,
    sample_date,
    job: IngestionJob,
) -> tuple[int, int]:
    created_count = 0
    updated_count = 0

    merged = defaultdict(lambda: {"artist": "", "item_count": 0, "weighted_score": 0})
    for (artist_key, _title_key), observation in song_observations.items():
        current = merged.setdefault(
            artist_key,
            {"artist": observation["artist"], "item_count": 0, "weighted_score": 0},
        )
        current["artist"] = observation["artist"]
        current["item_count"] += 1
        current["weighted_score"] += observation["weight"]

    for artist_key, payload in merged.items():
        artist = payload["artist"]
        item_count = payload["item_count"]
        weighted_score = payload["weighted_score"]
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
                                sample_date.strftime("%Y%m%d"): {
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

            sample_key = sample_date.strftime("%Y%m%d")
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


def _parse_sample_date(value: str):
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid sample date: {value}. Expected YYYYMMDD.") from exc


def _parse_start_month(value: str | None, today: date) -> tuple[int, int]:
    if value is None:
        return today.year, today.month
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError(f"Invalid start month: {value}. Expected YYYY-MM.") from exc
    return parsed.year, parsed.month


def _sample_dates_for_month(year: int, month: int, today: date) -> list[date]:
    samples = []
    for day in [15, 1]:
        sample = date(year, month, day)
        if sample <= today:
            samples.append(sample)
    return samples


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _filter_charts(
    groups: list[str] | None,
    exclude_groups: list[str],
    chart_keys: list[str] | None,
):
    excluded = set(exclude_groups)
    included = set(groups) if groups else None
    included_keys = set(chart_keys) if chart_keys else None
    charts = [
        chart
        for chart in CHART_TARGETS
        if chart.group not in excluded
        and (included is None or chart.group in included)
        and (included_keys is None or chart.key in included_keys)
    ]
    if not charts:
        raise ValueError("No chart targets selected.")
    return charts


def _is_earlier_observation(seed: ArtistSeed, sample_date) -> bool:
    current = (
        seed.first_observed_year or 9999,
        seed.first_observed_month or 99,
        seed.first_observed_sample_day or 99,
    )
    incoming = (sample_date.year, sample_date.month, sample_date.day)
    return incoming < current


def _is_later_observation(seed: ArtistSeed, sample_date) -> bool:
    current = (
        seed.last_observed_year or 0,
        seed.last_observed_month or 0,
        seed.last_observed_sample_day or 0,
    )
    incoming = (sample_date.year, sample_date.month, sample_date.day)
    return incoming > current


def _log(job: IngestionJob, level: str, message: str, context: dict) -> None:
    IngestionLog.objects.create(
        job=job,
        level=level,
        message=message,
        context=context,
    )
