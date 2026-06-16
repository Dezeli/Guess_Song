import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ingestion.models import IngestionJob, IngestionLog, RawCandidate

SOURCE_TYPE = RawCandidate.SourceType.B
DEFAULT_DATES = ["20260601", "20200115"]
USER_AGENT = "GuessSongCandidateCollector/0.1"
REQUEST_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class ChartTarget:
    key: str
    url: str
    date_param: str
    group: str
    row_limit: int = 100
    weight: int = 1

    def build_url(self, sample_date: str) -> str:
        separator = "&" if "?" in self.url else "?"
        return f"{self.url}{separator}{urlencode({self.date_param: sample_date})}"


CHART_TARGETS = [
    ChartTarget(
        "total",
        "https://music.bugs.co.kr/chart/track/week/total",
        "chartdate",
        "total",
        100,
        3,
    ),
    ChartTarget(
        "k_ballad",
        "https://music.bugs.co.kr/genre/chart/kpop/ballad/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "k_dance",
        "https://music.bugs.co.kr/genre/chart/kpop/dance/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "k_folk",
        "https://music.bugs.co.kr/genre/chart/kpop/folk/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "k_idol",
        "https://music.bugs.co.kr/genre/chart/kpop/idol/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "k_hiphop",
        "https://music.bugs.co.kr/genre/chart/kpop/rnh/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "k_rnb",
        "https://music.bugs.co.kr/genre/chart/kpop/rns/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "k_indie",
        "https://music.bugs.co.kr/genre/chart/kpop/indie/total/week",
        "date",
        "domestic",
    ),
    ChartTarget(
        "ost",
        "https://music.bugs.co.kr/genre/chart/etc/nost/total/week",
        "date",
        "etc",
    ),
    ChartTarget(
        "pop",
        "https://music.bugs.co.kr/genre/chart/pop/pop/total/week",
        "date",
        "overseas",
        20,
    ),
    ChartTarget(
        "pop_hiphop",
        "https://music.bugs.co.kr/genre/chart/pop/hiphop/total/week",
        "date",
        "overseas",
        20,
    ),
    ChartTarget(
        "pop_rnb",
        "https://music.bugs.co.kr/genre/chart/pop/rnb/total/week",
        "date",
        "overseas",
        20,
    ),
    ChartTarget(
        "pop_rock",
        "https://music.bugs.co.kr/genre/chart/pop/rock/total/week",
        "date",
        "overseas",
        20,
    ),
    ChartTarget(
        "jpop",
        "https://music.bugs.co.kr/genre/chart/etc/njpop/total/week",
        "date",
        "etc",
    ),
]

TRACK_ROW_RE = re.compile(
    r"<tr\b[^>]*\browType=[\"']track[\"'][^>]*>(?P<body>.*?)</tr>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_RE = re.compile(
    r"<p\b[^>]*class=[\"'][^\"']*\btitle\b[^\"']*[\"'][^>]*>.*?"
    r"<a\b[^>]*\btitle=[\"'](?P<title>[^\"']+)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
ARTIST_BLOCK_RE = re.compile(
    r"<p\b[^>]*class=[\"'][^\"']*\bartist\b[^\"']*[\"'][^>]*>(?P<body>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
ANCHOR_TEXT_RE = re.compile(r"<a\b[^>]*>(?P<text>.*?)</a>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WEEK_RANGE_RE = re.compile(
    r"(?P<start>\d{4}\.\d{2}\.\d{2})\s*~\s*(?P<end>\d{4}\.\d{2}\.\d{2})"
)


class Command(BaseCommand):
    help = "Collect minimal raw song candidates from sampled public chart pages."

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
            default=1.0,
            help="Delay in seconds between requests.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and parse without writing RawCandidate rows.",
        )

    def handle(self, *args, **options):
        sample_dates = [_parse_sample_date(raw) for raw in options["dates"]]
        dry_run = options["dry_run"]
        delay = max(options["delay"], 0)

        job = IngestionJob.objects.create(
            job_type="public_chart_sample",
            status=IngestionJob.Status.RUNNING,
            params={
                "source_type": SOURCE_TYPE,
                "sample_dates": [sample.strftime("%Y%m%d") for sample in sample_dates],
                "chart_count": len(CHART_TARGETS),
                "dry_run": dry_run,
            },
            started_at=timezone.now(),
        )

        total_candidates = 0
        created_candidates = 0
        skipped_pages = 0
        failed_pages = 0

        try:
            for chart in CHART_TARGETS:
                for sample in sample_dates:
                    page_url = chart.build_url(sample.strftime("%Y%m%d"))
                    try:
                        html = _fetch_html(page_url)
                        if not _response_matches_sample_date(html, sample):
                            skipped_pages += 1
                            _log(
                                job,
                                IngestionLog.Level.WARNING,
                                "Skipped fallback or mismatched chart page.",
                                {"chart": chart.key, "sample_date": sample.isoformat()},
                            )
                            continue

                        candidates = parse_chart_candidates(html)
                        total_candidates += len(candidates)
                        if dry_run:
                            created = 0
                        else:
                            created = save_candidates(candidates, sample, job)
                        created_candidates += created

                        _log(
                            job,
                            IngestionLog.Level.INFO,
                            "Collected chart sample.",
                            {
                                "chart": chart.key,
                                "sample_date": sample.isoformat(),
                                "parsed": len(candidates),
                                "created": created,
                            },
                        )
                    except Exception as exc:
                        failed_pages += 1
                        _log(
                            job,
                            IngestionLog.Level.ERROR,
                            "Failed to collect chart sample.",
                            {
                                "chart": chart.key,
                                "sample_date": sample.isoformat(),
                                "error": str(exc),
                            },
                        )
                    if delay:
                        time.sleep(delay)

            job.status = (
                IngestionJob.Status.FAILED
                if failed_pages == len(CHART_TARGETS) * len(sample_dates)
                else IngestionJob.Status.SUCCEEDED
            )
            job.total_count = total_candidates
            job.success_count = created_candidates
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
                f"{total_candidates} parsed candidates, "
                f"{created_candidates} new rows, "
                f"{skipped_pages} skipped pages, "
                f"{failed_pages} failed pages."
            )
        )


def _parse_sample_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid sample date: {value}. Expected YYYYMMDD.") from exc


def _fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _response_matches_sample_date(html: str, sample: date) -> bool:
    match = WEEK_RANGE_RE.search(_strip_tags(html))
    if not match:
        return False

    start = datetime.strptime(match.group("start"), "%Y.%m.%d").date()
    end = datetime.strptime(match.group("end"), "%Y.%m.%d").date()
    return start <= sample <= end


def parse_chart_candidates(html: str, row_limit: int | None = None) -> list[tuple[str, str]]:
    candidates = []
    seen = set()

    for row_index, row_match in enumerate(TRACK_ROW_RE.finditer(html), start=1):
        if row_limit is not None and row_index > row_limit:
            break
        row_html = row_match.group("body")
        title = _extract_title(row_html)
        artist = _extract_artist(row_html)
        if not title or not artist:
            continue

        key = (_normalize_raw_key(title), _normalize_raw_key(artist))
        if key in seen:
            continue
        seen.add(key)
        candidates.append((title, artist))

    return candidates


def parse_chart_artists(html: str, row_limit: int | None = None) -> list[str]:
    artists = []
    seen = set()

    for row_index, row_match in enumerate(TRACK_ROW_RE.finditer(html), start=1):
        if row_limit is not None and row_index > row_limit:
            break
        row_html = row_match.group("body")
        for artist in extract_artist_names(row_html):
            key = normalize_raw_key(artist)
            if not key or key in seen or _is_ignored_artist_key(key):
                continue
            seen.add(key)
            artists.append(artist)

    return artists


def parse_chart_artist_occurrences(
    html: str,
    row_limit: int | None = None,
) -> list[tuple[str, str]]:
    occurrences = []

    for row_index, row_match in enumerate(TRACK_ROW_RE.finditer(html), start=1):
        if row_limit is not None and row_index > row_limit:
            break
        row_html = row_match.group("body")
        title = _extract_title(row_html)
        if not title:
            continue
        for artist in extract_artist_names(row_html):
            key = normalize_raw_key(artist)
            if not key or _is_ignored_artist_key(key):
                continue
            occurrences.append((title, artist))

    return occurrences


def save_candidates(
    candidates: list[tuple[str, str]],
    sample_date: date,
    job: IngestionJob,
) -> int:
    created_count = 0
    for title, artist in candidates:
        title_key = _normalize_raw_key(title)
        artist_key = _normalize_raw_key(artist)
        if not title_key or not artist_key:
            continue

        try:
            with transaction.atomic():
                candidate, created = RawCandidate.objects.get_or_create(
                    source_type=SOURCE_TYPE,
                    raw_title_key=title_key,
                    raw_artist_key=artist_key,
                    defaults={
                        "job": job,
                        "raw_title": title,
                        "raw_artist": artist,
                        "first_observed_year": sample_date.year,
                        "first_observed_month": sample_date.month,
                        "first_observed_sample_day": sample_date.day,
                    },
                )
        except IntegrityError:
            created = False
            candidate = RawCandidate.objects.get(
                source_type=SOURCE_TYPE,
                raw_title_key=title_key,
                raw_artist_key=artist_key,
            )

        if created:
            created_count += 1
        elif _is_earlier_observation(candidate, sample_date):
            candidate.first_observed_year = sample_date.year
            candidate.first_observed_month = sample_date.month
            candidate.first_observed_sample_day = sample_date.day
            candidate.save(
                update_fields=[
                    "first_observed_year",
                    "first_observed_month",
                    "first_observed_sample_day",
                    "updated_at",
                ]
            )

    return created_count


def _extract_title(row_html: str) -> str:
    match = TITLE_RE.search(row_html)
    if not match:
        return ""
    return _clean_text(match.group("title"))


def _extract_artist(row_html: str) -> str:
    block_match = ARTIST_BLOCK_RE.search(row_html)
    if not block_match:
        return ""

    block = block_match.group("body")
    artists = []
    seen = set()
    for anchor in ANCHOR_TEXT_RE.finditer(block):
        artist = _clean_text(_strip_tags(anchor.group("text")))
        key = _normalize_raw_key(artist)
        if artist and key not in seen:
            seen.add(key)
            artists.append(artist)

    if artists:
        return ", ".join(artists)
    return _clean_text(_strip_tags(block))


def extract_artist_names(row_html: str) -> list[str]:
    block_match = ARTIST_BLOCK_RE.search(row_html)
    if not block_match:
        return []

    block = block_match.group("body")
    artists = []
    seen = set()
    for anchor in ANCHOR_TEXT_RE.finditer(block):
        artist = _clean_text(_strip_tags(anchor.group("text")))
        key = normalize_raw_key(artist)
        if artist and key not in seen:
            seen.add(key)
            artists.append(artist)

    if artists:
        return artists

    fallback_artist = _clean_text(_strip_tags(block))
    return [
        part
        for part in re.split(r"\s*(?:,|/|&|\band\b)\s*", fallback_artist)
        if part.strip()
    ]


def _is_earlier_observation(candidate: RawCandidate, sample_date: date) -> bool:
    if not candidate.first_observed_year or not candidate.first_observed_month:
        return True

    current = (
        candidate.first_observed_year,
        candidate.first_observed_month,
        candidate.first_observed_sample_day or 99,
    )
    incoming = (sample_date.year, sample_date.month, sample_date.day)
    return incoming < current


def _normalize_raw_key(value: str) -> str:
    return normalize_raw_key(value)


def normalize_raw_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _is_ignored_artist_key(key: str) -> bool:
    return key in {"various artists", "various artist", "original soundtrack", "unknown"}


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())


def _strip_tags(value: str) -> str:
    return TAG_RE.sub(" ", value)


def _log(job: IngestionJob, level: str, message: str, context: dict) -> None:
    IngestionLog.objects.create(
        job=job,
        level=level,
        message=message,
        context=context,
    )
