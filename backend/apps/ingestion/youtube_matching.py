import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from apps.catalog.models import YoutubeSource

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "GuessSongYouTubeMatcher/0.1"

AUTO_APPROVE_THRESHOLD = 90
REVIEW_THRESHOLD = 55

EXCLUDED_TERMS = [
    "cover",
    "reaction",
    "lyrics",
    "lyric",
    "가사",
    "노래방",
    "karaoke",
    "instrumental",
    "remix",
    "live",
    "라이브",
    "fancam",
    "직캠",
    "shorts",
    "short",
    "teaser",
    "티저",
    "dance practice",
    "stage",
    "무대",
    "performance video",
]

OFFICIAL_TITLE_TERMS = [
    "official mv",
    "official music video",
    "official video",
    "official audio",
    "mv",
    "music video",
    "m/v",
    "뮤직비디오",
]

OFFICIAL_CHANNEL_TERMS = [
    "official",
    "vevo",
    "hybe labels",
    "1thek",
    "stone music",
    "genie music",
    "smtown",
    "jyp entertainment",
    "yg entertainment",
    "starshiptv",
    "woolliment",
    "warner music",
    "sony music",
    "universal music",
]


@dataclass(frozen=True)
class VideoCandidate:
    video_id: str
    title: str
    channel_title: str
    channel_id: str
    duration_seconds: int | None
    view_count: int | None
    published_at: str | None


@dataclass(frozen=True)
class MatchDecision:
    action: str
    source_type: str | None = None
    official_score: int = 0
    reason: str = ""
    video: VideoCandidate | None = None
    review_candidates: tuple[dict, ...] = ()


def find_youtube_match(title: str, artist: str, max_results: int = 8) -> MatchDecision:
    videos = search_videos(title=title, artist=artist, max_results=max_results)
    if not videos:
        return MatchDecision(action="reject", reason="no_youtube_results")

    decisions = [_score_video(video, title=title, artist=artist) for video in videos]
    approved = [decision for decision in decisions if decision.action == "approve"]
    if approved:
        return max(approved, key=lambda decision: decision.official_score)

    review = [
        decision
        for decision in decisions
        if decision.action == "review" and decision.official_score >= REVIEW_THRESHOLD
    ]
    if review:
        review_payload = tuple(
            {
                "video_id": decision.video.video_id,
                "title": decision.video.title,
                "channel_title": decision.video.channel_title,
                "official_score": decision.official_score,
                "reason": decision.reason,
            }
            for decision in sorted(review, key=lambda item: item.official_score, reverse=True)[:5]
            if decision.video
        )
        return MatchDecision(
            action="review",
            reason="ambiguous_youtube_match",
            official_score=max(item.official_score for item in review),
            review_candidates=review_payload,
        )

    return MatchDecision(action="reject", reason="no_official_youtube_match")


def search_videos(title: str, artist: str, max_results: int = 8) -> list[VideoCandidate]:
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured.")

    query = f"{artist} {title} official"
    search_payload = _youtube_get(
        "/search",
        {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "videoEmbeddable": "true",
            "key": api_key,
        },
    )
    video_ids = [
        item.get("id", {}).get("videoId")
        for item in search_payload.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    if not video_ids:
        return []

    video_payload = _youtube_get(
        "/videos",
        {
            "part": "snippet,contentDetails,statistics,status",
            "id": ",".join(video_ids),
            "key": api_key,
        },
    )

    videos = []
    for item in video_payload.get("items", []):
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        videos.append(
            VideoCandidate(
                video_id=item["id"],
                title=snippet.get("title", ""),
                channel_title=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                duration_seconds=_parse_iso8601_duration(content_details.get("duration", "")),
                view_count=_parse_int(statistics.get("viewCount")),
                published_at=snippet.get("publishedAt"),
            )
        )
    return videos


def build_youtube_source_defaults(decision: MatchDecision) -> dict:
    if decision.video is None or decision.source_type is None:
        raise ValueError("Approved decision requires a video and source type.")

    published_at = None
    if decision.video.published_at:
        published_at = datetime.fromisoformat(decision.video.published_at.replace("Z", "+00:00"))

    return {
        "title": decision.video.title,
        "channel_title": decision.video.channel_title,
        "channel_id": decision.video.channel_id,
        "duration_seconds": decision.video.duration_seconds,
        "view_count": decision.video.view_count,
        "published_at": published_at,
        "source_type": decision.source_type,
        "priority": _source_priority(decision.source_type),
        "official_score": decision.official_score,
        "status": YoutubeSource.Status.APPROVED,
        "raw_payload": {"match_reason": decision.reason},
    }


def _score_video(video: VideoCandidate, title: str, artist: str) -> MatchDecision:
    title_key = _normalize(title)
    artist_key = _normalize(artist)
    video_title_key = _normalize(video.title)
    channel_key = _normalize(video.channel_title)
    combined_key = f"{video_title_key} {channel_key}"

    if any(term in combined_key for term in EXCLUDED_TERMS):
        return MatchDecision(
            action="reject",
            reason="excluded_video_term",
            official_score=0,
            video=video,
        )

    score = 0
    reasons = []

    if title_key and title_key in video_title_key:
        score += 35
        reasons.append("title_match")
    elif _loose_contains(video_title_key, title_key):
        score += 20
        reasons.append("loose_title_match")

    if artist_key and (artist_key in video_title_key or artist_key in channel_key):
        score += 25
        reasons.append("artist_match")
    elif _loose_contains(channel_key, artist_key):
        score += 15
        reasons.append("loose_artist_match")

    source_type = None
    if channel_key.endswith(" topic") or " topic" in channel_key:
        score += 35
        source_type = YoutubeSource.SourceType.TOPIC_ART_TRACK
        reasons.append("topic_channel")
    elif any(term in video_title_key for term in ["official mv", "official music video", "mv"]):
        score += 25
        source_type = YoutubeSource.SourceType.OFFICIAL_MV
        reasons.append("official_mv_title")
    elif "official audio" in video_title_key or "audio" in video_title_key:
        score += 20
        source_type = YoutubeSource.SourceType.OFFICIAL_AUDIO
        reasons.append("official_audio_title")

    if any(term in channel_key for term in OFFICIAL_CHANNEL_TERMS):
        score += 20
        if source_type is None:
            source_type = YoutubeSource.SourceType.ARTIST_CHANNEL
        reasons.append("official_channel")

    if any(term in video_title_key for term in OFFICIAL_TITLE_TERMS):
        score += 10
        reasons.append("official_title_signal")

    if source_type is None and ("records" in channel_key or "entertainment" in channel_key):
        source_type = YoutubeSource.SourceType.LABEL_CHANNEL
        score += 10
        reasons.append("label_like_channel")

    score = min(score, 100)
    reason = ",".join(reasons) or "weak_match"

    if score >= AUTO_APPROVE_THRESHOLD and source_type is not None:
        return MatchDecision(
            action="approve",
            source_type=source_type,
            official_score=score,
            reason=reason,
            video=video,
        )
    if score >= REVIEW_THRESHOLD:
        return MatchDecision(
            action="review",
            source_type=source_type,
            official_score=score,
            reason=reason,
            video=video,
        )
    return MatchDecision(action="reject", reason=reason, official_score=score, video=video)


def _youtube_get(path: str, params: dict) -> dict:
    url = f"{YOUTUBE_API_BASE}{path}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", normalized)
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _loose_contains(container: str, needle: str) -> bool:
    if not container or not needle:
        return False
    compact_container = container.replace(" ", "")
    compact_needle = needle.replace(" ", "")
    return len(compact_needle) >= 3 and compact_needle in compact_container


def _parse_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _parse_iso8601_duration(value: str) -> int | None:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?T?"
        r"(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?"
        r"(?:(?P<seconds>\d+)S)?",
        value or "",
    )
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _source_priority(source_type: str) -> int:
    return {
        YoutubeSource.SourceType.OFFICIAL_MV: 10,
        YoutubeSource.SourceType.OFFICIAL_AUDIO: 20,
        YoutubeSource.SourceType.TOPIC_ART_TRACK: 30,
        YoutubeSource.SourceType.LABEL_CHANNEL: 40,
        YoutubeSource.SourceType.ARTIST_CHANNEL: 50,
    }.get(source_type, 100)
