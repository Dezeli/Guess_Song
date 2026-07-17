import csv
import json
import re
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ingestion.management.commands.discover_youtube_artist_videos import (
    _infer_artist_and_song_title,
)
from apps.ingestion.models import ArtistSeed
from apps.ingestion.youtube_matching import (
    VideoCandidate,
    _require_youtube_api_keys,
    _youtube_get,
    build_artist_mv_query,
    score_artist_video,
)

NEGATIVE_TERMS = [
    "cover",
    "lyrics",
    "lyric",
    "karaoke",
    "reaction",
    "fancam",
    "shorts",
    "teaser",
    "커버",
    "가사",
    "노래방",
    "직캠",
    "쇼츠",
    "티저",
]

QUERY_TYPES = ["basic_mv", "negative_mv"]


class Command(BaseCommand):
    help = "Probe and cache YouTube artist search query variants for manual quality review."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of top pending ArtistSeed rows to probe.",
        )
        parser.add_argument(
            "--max-results",
            type=int,
            default=25,
            help="YouTube search results per query. YouTube allows up to 50.",
        )
        parser.add_argument(
            "--output-dir",
            default="data/youtube_query_probe/top10_basic_vs_negative",
            help="Output directory. Existing raw JSON files are reused and not re-fetched.",
        )
        parser.add_argument(
            "--force-fetch",
            action="store_true",
            help="Fetch again even when raw JSON cache files already exist.",
        )

    def handle(self, *args, **options):
        _require_youtube_api_keys()

        limit = max(options["limit"], 1)
        max_results = min(max(options["max_results"], 1), 50)
        output_dir = Path(options["output_dir"])
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        seeds = list(
            ArtistSeed.objects.filter(status=ArtistSeed.Status.PENDING)
            .order_by("-observed_weight_score", "-observed_count", "id")[:limit]
        )
        if not seeds:
            raise RuntimeError("No pending ArtistSeed rows found.")

        artists_rows = []
        result_rows = []
        summary_rows = []
        fetched_count = 0
        cache_hit_count = 0

        for artist_rank, seed in enumerate(seeds, start=1):
            artists_rows.append(_artist_row(artist_rank, seed))
            queries = _query_variants(seed.display_artist or seed.raw_artist)
            for query_type in QUERY_TYPES:
                query = queries[query_type]
                cache_path = raw_dir / _cache_filename(artist_rank, seed.display_artist, query_type)
                if cache_path.exists() and not options["force_fetch"]:
                    payload = json.loads(cache_path.read_text(encoding="utf-8"))
                    cache_hit_count += 1
                else:
                    payload = _youtube_search(query=query, max_results=max_results)
                    cache_path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    fetched_count += 1

                videos = _videos_from_search_payload(payload)
                scored_rows = [
                    _result_row(
                        artist_rank=artist_rank,
                        seed=seed,
                        query_type=query_type,
                        query=query,
                        position=position,
                        video=video,
                    )
                    for position, video in enumerate(videos, start=1)
                ]
                result_rows.extend(scored_rows)
                summary_rows.append(_summary_row(artist_rank, seed, query_type, query, scored_rows))

        _write_csv(output_dir / "artists.csv", artists_rows)
        _write_csv(output_dir / "query_results.csv", result_rows)
        _write_csv(output_dir / "query_summary.csv", summary_rows)
        _write_manifest(
            output_dir=output_dir,
            limit=limit,
            max_results=max_results,
            fetched_count=fetched_count,
            cache_hit_count=cache_hit_count,
            artists=artists_rows,
        )
        _write_report(
            output_dir=output_dir,
            fetched_count=fetched_count,
            cache_hit_count=cache_hit_count,
            artists=artists_rows,
            summaries=summary_rows,
            results=result_rows,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote probe output to {output_dir}. "
                f"Fetched {fetched_count} search response(s), "
                f"reused {cache_hit_count} cache file(s)."
            )
        )


def _artist_row(rank: int, seed: ArtistSeed) -> dict:
    return {
        "rank": rank,
        "artist_seed_id": seed.id,
        "display_artist": seed.display_artist,
        "raw_artist": seed.raw_artist,
        "observed_weight_score": seed.observed_weight_score,
        "observed_count": seed.observed_count,
        "observed_sample_count": seed.observed_sample_count,
        "first_observed": _observed_date(seed, "first"),
        "last_observed": _observed_date(seed, "last"),
    }


def _observed_date(seed: ArtistSeed, prefix: str) -> str:
    year = getattr(seed, f"{prefix}_observed_year")
    month = getattr(seed, f"{prefix}_observed_month")
    day = getattr(seed, f"{prefix}_observed_sample_day")
    if not year or not month or not day:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _query_variants(artist: str) -> dict[str, str]:
    basic_query = build_artist_mv_query(artist)
    negative_query = " ".join([basic_query, *[f"-{term}" for term in NEGATIVE_TERMS]])
    return {
        "basic_mv": basic_query,
        "negative_mv": negative_query,
    }


def _cache_filename(artist_rank: int, artist: str, query_type: str) -> str:
    return f"{artist_rank:02d}_{_slug(artist)}_{query_type}.json"


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE)
    normalized = normalized.strip("_")
    return normalized[:80] or "artist"


def _youtube_search(query: str, max_results: int) -> dict:
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": max_results,
        "videoEmbeddable": "true",
    }
    return _youtube_get("/search", params)


def _videos_from_search_payload(payload: dict) -> list[VideoCandidate]:
    videos = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        videos.append(
            VideoCandidate(
                video_id=video_id,
                title=snippet.get("title", ""),
                channel_title=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                duration_seconds=None,
                view_count=None,
                published_at=snippet.get("publishedAt"),
                embeddable=True,
            )
        )
    return videos


def _result_row(
    *,
    artist_rank: int,
    seed: ArtistSeed,
    query_type: str,
    query: str,
    position: int,
    video: VideoCandidate,
) -> dict:
    artist_name, song_title = _infer_artist_and_song_title(
        video.title,
        seed.display_artist or seed.raw_artist,
    )
    decision = score_artist_video(video, artist=seed.display_artist or seed.raw_artist)
    return {
        "artist_rank": artist_rank,
        "artist_seed_id": seed.id,
        "seed_artist": seed.display_artist,
        "query_type": query_type,
        "query": query,
        "position": position,
        "video_id": video.video_id,
        "youtube_url": f"https://www.youtube.com/watch?v={video.video_id}",
        "youtube_title": video.title,
        "channel_title": video.channel_title,
        "channel_id": video.channel_id,
        "published_at": video.published_at or "",
        "inferred_artist": artist_name,
        "inferred_song_title": song_title,
        "action": decision.action,
        "source_type": decision.source_type or "",
        "official_score": decision.official_score,
        "reason": decision.reason,
    }


def _summary_row(
    artist_rank: int,
    seed: ArtistSeed,
    query_type: str,
    query: str,
    scored_rows: list[dict],
) -> dict:
    qualified = [row for row in scored_rows if int(row["official_score"]) >= 70]
    review = [
        row
        for row in scored_rows
        if 50 <= int(row["official_score"]) < 70
    ]
    rejected = [row for row in scored_rows if int(row["official_score"]) < 50]
    top = max(scored_rows, key=lambda row: int(row["official_score"]), default=None)
    return {
        "artist_rank": artist_rank,
        "artist_seed_id": seed.id,
        "seed_artist": seed.display_artist,
        "query_type": query_type,
        "query": query,
        "result_count": len(scored_rows),
        "qualified_count": len(qualified),
        "review_count": len(review),
        "rejected_count": len(rejected),
        "top_official_score": top["official_score"] if top else "",
        "top_action": top["action"] if top else "",
        "top_title": top["youtube_title"] if top else "",
        "top_channel": top["channel_title"] if top else "",
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(
    *,
    output_dir: Path,
    limit: int,
    max_results: int,
    fetched_count: int,
    cache_hit_count: int,
    artists: list[dict],
) -> None:
    manifest = {
        "generated_at": timezone.now().isoformat(),
        "command": "probe_youtube_artist_queries",
        "limit": limit,
        "max_results": max_results,
        "query_types": QUERY_TYPES,
        "negative_terms": NEGATIVE_TERMS,
        "fetched_search_responses": fetched_count,
        "cache_hit_search_responses": cache_hit_count,
        "artists": artists,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_report(
    *,
    output_dir: Path,
    fetched_count: int,
    cache_hit_count: int,
    artists: list[dict],
    summaries: list[dict],
    results: list[dict],
) -> None:
    lines = [
        "# YouTube Artist Query Probe",
        "",
        f"- Generated at: {timezone.now().isoformat()}",
        f"- Fetched search responses: {fetched_count}",
        f"- Reused cached search responses: {cache_hit_count}",
        f"- Query types: {', '.join(QUERY_TYPES)}",
        f"- Negative terms: {', '.join(NEGATIVE_TERMS)}",
        "",
        "## Artists",
        "",
        "| Rank | Artist | Score | Observed | Samples |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for row in artists:
        lines.append(
            "| {rank} | {display_artist} | {observed_weight_score} | "
            "{observed_count} | {observed_sample_count} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Query Summary",
            "",
            "| Artist | Query Type | Results | Qualified >=70 | Review 50-69 | "
            "Rejected <50 | Top Score | Top Title | Top Channel |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in summaries:
        lines.append(
            "| {seed_artist} | {query_type} | {result_count} | {qualified_count} | "
            "{review_count} | {rejected_count} | {top_official_score} | {top_title} | "
            "{top_channel} |".format(**{key: _md_cell(value) for key, value in row.items()})
        )

    lines.extend(
        [
            "",
            "## Top Rows By Artist And Query",
            "",
            "Only the first 10 rows for each artist/query are shown here. "
            "See `query_results.csv` for every row.",
        ]
    )
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in results:
        grouped.setdefault((row["seed_artist"], row["query_type"]), []).append(row)

    for (artist, query_type), rows in grouped.items():
        lines.extend(
            [
                "",
                f"### {artist} / {query_type}",
                "",
                "| Pos | Score | Action | Title | Channel | Reason |",
                "| ---: | ---: | --- | --- | --- | --- |",
            ]
        )
        for row in rows[:10]:
            lines.append(
                "| {position} | {official_score} | {action} | {youtube_title} | "
                "{channel_title} | {reason} |".format(
                    **{key: _md_cell(value) for key, value in row.items()}
                )
            )

    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_cell(value) -> str:
    serialized = "" if value is None else str(value)
    return serialized.replace("|", "\\|").replace("\n", " ")
