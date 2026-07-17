import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from apps.catalog.models import YoutubeSource

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "GuessSongYouTubeMatcher/0.1"

AUTO_APPROVE_THRESHOLD = 90
REVIEW_THRESHOLD = 50
ARTIST_DISCOVERY_SCORE_THRESHOLD = 70
ARTIST_DISCOVERY_PAGE_SIZE = 20
ARTIST_DISCOVERY_CONTINUE_MIN_MATCHES = 13

QUOTA_ERROR_REASONS = {
    "dailyLimitExceeded",
    "quotaExceeded",
    "userRateLimitExceeded",
}

_current_api_key_index = 0
_exhausted_api_key_indexes: set[int] = set()

EXCLUDED_TERMS = [
    "cover",
    "커버",
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
    "쇼츠",
    "teaser",
    "티저",
    "stage",
    "무대",
    "playlist",
    "플레이리스트",
    "모음",
]

REVIEW_TERMS = [
    "performance video",
    "performance ver",
    "performance version",
    "dance practice",
    "댄스 연습",
    "dance ver",
    "dance version",
    "choreography video",
    "track video",
    "drama ver",
    "drama version",
]

EXCLUDED_CHANNEL_TERMS = [
    "japan",
]

EXCLUDED_TERMS.extend(["unofficial"])
REVIEW_TERMS.extend(["visualizer"])
REVIEW_TERMS.extend(["special clip"])
EXCLUDED_CHANNEL_TERMS.extend(["fan channel"])

OFFICIAL_TITLE_TERMS = [
    "official mv",
    "official music video",
    "official video",
    "official audio",
    "mv",
    "music video",
    "m/v",
    "m v",
    "뮤직비디오",
]

OFFICIAL_CHANNEL_TERMS = [
    "vevo",
    "hybe labels",
    "1thek",
    "super sound bugs",
    "stone music",
    "genie music",
    "smtown",
    "jyp entertainment",
    "yg entertainment",
    "starship",
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
    embeddable: bool | None


@dataclass(frozen=True)
class MatchDecision:
    action: str
    source_type: str | None = None
    official_score: int = 0
    reason: str = ""
    video: VideoCandidate | None = None
    review_candidates: tuple[dict, ...] = ()


@dataclass(frozen=True)
class VideoSearchPage:
    videos: tuple[VideoCandidate, ...]
    next_page_token: str | None = None
    total_results: int | None = None


class YouTubeQuotaExhausted(RuntimeError):
    """Raised when every configured YouTube API key has hit quota."""


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
    _require_youtube_api_keys()

    query = f"{artist} {title} official"
    search_payload = _youtube_get(
        "/search",
        {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "videoEmbeddable": "true",
            "videoSyndicated": "true",
        },
    )
    video_ids = [
        item.get("id", {}).get("videoId")
        for item in search_payload.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    return list(_fetch_video_details(video_ids))


def search_artist_mv_videos(
    artist: str,
    max_results: int = ARTIST_DISCOVERY_PAGE_SIZE,
    page_token: str | None = None,
) -> VideoSearchPage:
    _require_youtube_api_keys()

    params = {
        "part": "snippet",
        "type": "video",
        "q": build_artist_mv_query(artist),
        "maxResults": max_results,
        "videoEmbeddable": "true",
        "videoSyndicated": "true",
    }
    if page_token:
        params["pageToken"] = page_token

    search_payload = _youtube_get("/search", params)
    video_ids = [
        item.get("id", {}).get("videoId")
        for item in search_payload.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    page_info = search_payload.get("pageInfo", {})
    total_results = _parse_int(page_info.get("totalResults"))

    return VideoSearchPage(
        videos=_fetch_video_details(video_ids),
        next_page_token=search_payload.get("nextPageToken"),
        total_results=total_results,
    )


def score_artist_video(video: VideoCandidate, artist: str) -> MatchDecision:
    return _score_video(video, title="", artist=artist)


def build_artist_mv_query(artist: str) -> str:
    return f"{_display_artist_query_name(artist)} mv"


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
        "raw_payload": {
            "match_reason": decision.reason,
            "embeddable": decision.video.embeddable,
        },
    }


def _fetch_video_details(video_ids: list[str]) -> tuple[VideoCandidate, ...]:
    if not video_ids:
        return ()

    video_payload = _youtube_get(
        "/videos",
        {
            "part": "snippet,contentDetails,statistics,status",
            "id": ",".join(video_ids),
        },
    )

    videos = []
    for item in video_payload.get("items", []):
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        status = item.get("status", {})
        videos.append(
            VideoCandidate(
                video_id=item["id"],
                title=snippet.get("title", ""),
                channel_title=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                duration_seconds=_parse_iso8601_duration(content_details.get("duration", "")),
                view_count=_parse_int(statistics.get("viewCount")),
                published_at=snippet.get("publishedAt"),
                embeddable=status.get("embeddable"),
            )
        )
    return tuple(videos)


def _score_video(video: VideoCandidate, title: str, artist: str) -> MatchDecision:
    if video.embeddable is False:
        return MatchDecision(
            action="reject",
            reason="not_embeddable",
            official_score=0,
            video=video,
        )

    title_key = _normalize(title)
    artist_aliases = _artist_aliases(artist)
    video_title_key = _normalize(video.title)
    video_signal_title_key = _normalize_for_signal(video.title)
    channel_key = _normalize_for_signal(video.channel_title)
    combined_key = f"{video_title_key} {video_signal_title_key} {channel_key}"

    if _has_excluded_term(combined_key):
        return MatchDecision(
            action="reject",
            reason="excluded_video_term",
            official_score=0,
            video=video,
        )
    if any(term in channel_key for term in EXCLUDED_CHANNEL_TERMS):
        return MatchDecision(
            action="reject",
            reason="excluded_channel_term",
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

    artist_matched = False
    if _any_alias_in_text(artist_aliases, video_title_key, video_signal_title_key):
        score += 25
        reasons.append("artist_match")
        artist_matched = True
    elif _any_alias_in_text(artist_aliases, channel_key) or any(
        _loose_contains(channel_key, alias) for alias in artist_aliases
    ):
        score += 15
        reasons.append("channel_artist_match")
        artist_matched = True

    source_type = None
    if channel_key.endswith(" topic") or " topic" in channel_key:
        score += 35
        source_type = YoutubeSource.SourceType.TOPIC_ART_TRACK
        reasons.append("topic_channel")
    elif _has_official_mv_signal(video_signal_title_key):
        score += 35
        source_type = YoutubeSource.SourceType.OFFICIAL_MV
        reasons.append("official_mv_title")
    elif "official audio" in video_title_key or "audio" in video_title_key:
        score += 20
        source_type = YoutubeSource.SourceType.OFFICIAL_AUDIO
        reasons.append("official_audio_title")

    if _has_official_channel_signal(channel_key):
        score += 20
        if source_type is None:
            source_type = YoutubeSource.SourceType.ARTIST_CHANNEL
        reasons.append("official_channel")
    elif "official" in channel_key and _any_alias_in_text(artist_aliases, channel_key):
        score += 20
        if source_type is None:
            source_type = YoutubeSource.SourceType.ARTIST_CHANNEL
        reasons.append("artist_official_channel")
    elif channel_key in artist_aliases or (
        source_type == YoutubeSource.SourceType.OFFICIAL_MV
        and _any_alias_in_text(artist_aliases, channel_key)
    ):
        score += 20
        if source_type is None:
            source_type = YoutubeSource.SourceType.ARTIST_CHANNEL
        reasons.append("artist_channel")

    if any(term in video_signal_title_key for term in OFFICIAL_TITLE_TERMS):
        score += 10
        reasons.append("official_title_signal")

    if source_type is None and _has_label_channel_signal(channel_key):
        source_type = YoutubeSource.SourceType.LABEL_CHANNEL
        score += 10
        reasons.append("label_like_channel")

    if any(term in combined_key for term in REVIEW_TERMS):
        score = min(max(score, REVIEW_THRESHOLD), ARTIST_DISCOVERY_SCORE_THRESHOLD - 1)
        reasons.append("review_video_term")

    if not artist_matched:
        score = min(score, REVIEW_THRESHOLD - 1)
        reasons.append("no_artist_match")
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
    global _current_api_key_index

    api_keys = _configured_api_keys()
    if not api_keys:
        raise RuntimeError("No YouTube API key is configured.")

    quota_errors = []
    for key_index, key in _iter_available_api_keys(api_keys):
        request_params = {**params, "key": key}
        try:
            payload = _youtube_get_with_key(path, request_params)
            _current_api_key_index = key_index
            return payload
        except HTTPError as exc:
            error_payload = _http_error_payload(exc)
            if _is_quota_error(exc, error_payload):
                _exhausted_api_key_indexes.add(key_index)
                quota_errors.append(_youtube_error_reason(error_payload) or f"HTTP {exc.code}")
                continue
            reason = _youtube_error_reason(error_payload)
            raise RuntimeError(
                f"YouTube API request failed: HTTP {exc.code} {reason or exc.reason}"
            ) from exc

    detail = ", ".join(quota_errors) or "quota exhausted"
    raise YouTubeQuotaExhausted(f"All configured YouTube API keys are exhausted: {detail}")


def _youtube_get_with_key(path: str, params: dict) -> dict:
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


def _require_youtube_api_keys() -> None:
    if not _configured_api_keys():
        raise RuntimeError("YOUTUBE_API_KEY1 or YOUTUBE_API_KEY2 is not configured.")


def _configured_api_keys() -> list[str]:
    keys = list(getattr(settings, "YOUTUBE_API_KEYS", []))
    legacy_key = getattr(settings, "YOUTUBE_API_KEY", "")
    if legacy_key:
        keys.append(legacy_key)

    result = []
    seen = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _iter_available_api_keys(api_keys: list[str]):
    key_count = len(api_keys)
    for offset in range(key_count):
        key_index = (_current_api_key_index + offset) % key_count
        if key_index in _exhausted_api_key_indexes:
            continue
        yield key_index, api_keys[key_index]


def _http_error_payload(exc: HTTPError) -> dict:
    try:
        raw_body = exc.read().decode("utf-8")
    except Exception:
        return {}
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return {}


def _is_quota_error(exc: HTTPError, payload: dict) -> bool:
    if exc.code not in {403, 429}:
        return False
    reason = _youtube_error_reason(payload)
    if reason in QUOTA_ERROR_REASONS:
        return True
    message = _youtube_error_message(payload).casefold()
    return "quota" in message or "daily limit" in message


def _youtube_error_reason(payload: dict) -> str:
    errors = payload.get("error", {}).get("errors", [])
    if errors:
        return errors[0].get("reason", "")
    return payload.get("error", {}).get("status", "")


def _youtube_error_message(payload: dict) -> str:
    return payload.get("error", {}).get("message", "")


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", normalized)
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _normalize_for_signal(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _has_excluded_term(value: str) -> bool:
    for term in EXCLUDED_TERMS:
        if term not in value:
            continue
        if term in {"playlist", "플레이리스트"}:
            if any(pattern in value for pattern in ["mv playlist", "music video playlist"]):
                return True
            continue
        return True
    return any(pattern in value for pattern in ["노래모음", "모아보기", "뮤비 모음"])


def _has_official_mv_signal(value: str) -> bool:
    return (
        "official mv" in value
        or "official music video" in value
        or "music video" in value
        or "뮤직비디오" in value
        or _has_token(value, "mv")
        or ("m v" in value)
    )


def _has_official_channel_signal(value: str) -> bool:
    return any(term in value for term in OFFICIAL_CHANNEL_TERMS) or _has_label_channel_signal(value)


def _has_label_channel_signal(value: str) -> bool:
    return (
        "entertainment" in value
        or "music" in value
        or "records" in value
        or "labels" in value
        or "label" in value
    )


def _has_token(value: str, token: str) -> bool:
    return token in value.split()


def _artist_aliases(artist: str) -> tuple[str, ...]:
    aliases = [_normalize(alias) for alias in _display_artist_aliases(artist)]
    seen = set()
    result = []
    for alias in aliases:
        if len(alias.replace(" ", "")) < 2 or alias in seen:
            continue
        seen.add(alias)
        result.append(alias)
    return tuple(result)


def _display_artist_aliases(artist: str) -> tuple[str, ...]:
    aliases = []
    stripped = re.sub(r"[()[\]]+", " ", artist or "")
    aliases.append(stripped)
    for match in re.findall(r"\(([^)]*)\)|\[([^\]]*)\]", artist or ""):
        aliases.extend(part for part in match if part)
    aliases.extend(part for part in re.split(r"\s*[()/,&]\s*", artist or ""))

    seen = set()
    result = []
    for alias in aliases:
        alias = " ".join(alias.split())
        normalized = _normalize(alias)
        if len(normalized.replace(" ", "")) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        result.append(alias)
    return tuple(result)


def _display_artist_query_name(artist: str) -> str:
    query_name = re.split(r"\s*[\[(]", artist or "", maxsplit=1)[0]
    if not query_name.strip():
        query_name = re.sub(r"[()[\]]+", " ", artist or "")
    return " ".join(query_name.split())


def _any_alias_in_text(aliases: tuple[str, ...], *texts: str) -> bool:
    return any(alias and any(alias in text for text in texts) for alias in aliases)


def _loose_contains(container: str, needle: str) -> bool:
    if not container or not needle:
        return False
    compact_container = container.replace(" ", "")
    compact_needle = needle.replace(" ", "")
    return len(compact_needle) >= 3 and compact_needle in compact_container


def _parse_int(value: str | int | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
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
