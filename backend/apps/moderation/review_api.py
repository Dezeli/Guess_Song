from django.conf import settings
from django.db import transaction
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.ingestion.management.commands.promote_discovered_youtube_videos import (
    DEFAULT_PACK_NAME,
    _next_pack_order,
    _promote_candidate,
)
from apps.ingestion.models import DiscoveredYoutubeVideo, IngestionJob
from apps.quizzes.models import QuizPack, QuizQuestion

router = Router(tags=["review"])

SESSION_KEY = "review_admin_authenticated"


class ReviewLoginIn(Schema):
    password: str


class ReviewSessionOut(Schema):
    authenticated: bool


class YoutubeCandidateOut(Schema):
    id: int
    song_title: str
    artist_name: str
    youtube_title: str
    youtube_url: str
    video_id: str
    channel_title: str
    channel_id: str
    uploaded_year: int | None
    uploaded_month: int | None
    official_score: int
    source_type: str
    status: str
    review_reason: str
    duration_seconds: int | None
    view_count: int | None
    created_at: str
    updated_at: str


class YoutubeCandidateListOut(Schema):
    candidates: list[YoutubeCandidateOut]
    total: int


class ReviewCandidateUpdateIn(Schema):
    song_title: str
    artist_name: str


class ReviewRejectIn(Schema):
    reason: str = ""


class ReviewActionOut(Schema):
    candidate: YoutubeCandidateOut
    result: str
    reason: str = ""


@router.post("/review/login", response=ReviewSessionOut)
def review_login(request, payload: ReviewLoginIn):
    configured_password = settings.REVIEW_ADMIN_PASSWORD
    if not configured_password:
        raise HttpError(503, "Review password is not configured.")
    if payload.password != configured_password:
        raise HttpError(401, "Invalid review password.")
    request.session[SESSION_KEY] = True
    return {"authenticated": True}


@router.get("/review/session", response=ReviewSessionOut)
def review_session(request):
    return {"authenticated": _is_authenticated(request)}


@router.post("/review/logout", response=ReviewSessionOut)
def review_logout(request):
    request.session.pop(SESSION_KEY, None)
    return {"authenticated": False}


@router.get("/review/youtube-candidates", response=YoutubeCandidateListOut)
def list_youtube_candidates(
    request,
    status: str = DiscoveredYoutubeVideo.Status.REVIEW_REQUIRED,
    limit: int = 50,
):
    _require_review_auth(request)
    limit = min(max(limit, 1), 100)
    candidates = (
        DiscoveredYoutubeVideo.objects.filter(status=status)
        .order_by("-official_score", "artist_name", "song_title", "id")[:limit]
    )
    total = DiscoveredYoutubeVideo.objects.filter(status=status).count()
    return {
        "candidates": [_serialize_candidate(candidate) for candidate in candidates],
        "total": total,
    }


@router.get("/review/youtube-candidates/{candidate_id}", response=YoutubeCandidateOut)
def get_youtube_candidate(request, candidate_id: int):
    _require_review_auth(request)
    return _serialize_candidate(_get_candidate(candidate_id))


@router.post("/review/youtube-candidates/{candidate_id}/approve", response=ReviewActionOut)
def approve_youtube_candidate(request, candidate_id: int, payload: ReviewCandidateUpdateIn):
    _require_review_auth(request)
    song_title = _clean(payload.song_title)
    artist_name = _clean(payload.artist_name)
    if not song_title or not artist_name:
        raise HttpError(400, "Title and artist are required.")

    with transaction.atomic():
        candidate = DiscoveredYoutubeVideo.objects.select_for_update().get(id=candidate_id)
        candidate.song_title = song_title
        candidate.artist_name = artist_name
        candidate.status = DiscoveredYoutubeVideo.Status.DISCOVERED
        candidate.raw_payload = {
            **candidate.raw_payload,
            "manual_review": {
                "action": "approve",
                "reviewed_at": timezone.now().isoformat(),
            },
        }
        candidate.save(
            update_fields=["song_title", "artist_name", "status", "raw_payload", "updated_at"]
        )

        pack, _ = QuizPack.objects.get_or_create(
            name=DEFAULT_PACK_NAME,
            defaults={
                "description": "Automatically promoted from artist-first YouTube discovery.",
                "is_public": True,
            },
        )
        job = IngestionJob.objects.create(
            job_type="youtube_discovered_manual_review",
            status=IngestionJob.Status.RUNNING,
            params={
                "discovered_youtube_video_id": candidate.id,
                "action": "approve",
                "quiz_pack_name": DEFAULT_PACK_NAME,
            },
            total_count=1,
            started_at=timezone.now(),
        )
        try:
            result = _promote_candidate(
                candidate,
                job=job,
                pack=pack,
                next_pack_order=_next_pack_order(pack),
                min_score=0,
                question_status=QuizQuestion.Status.APPROVED,
                allow_manual_review_override=True,
            )
        except Exception as exc:
            job.status = IngestionJob.Status.FAILED
            job.fail_count = 1
            job.error_message = str(exc)
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "fail_count", "error_message", "finished_at"])
            raise

        job.status = IngestionJob.Status.SUCCEEDED
        job.success_count = int(result.counter in {"promoted", "duplicate"})
        job.fail_count = int(result.counter == "review")
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "success_count", "fail_count", "finished_at"])

    candidate.refresh_from_db()
    return {
        "candidate": _serialize_candidate(candidate),
        "result": result.counter,
        "reason": result.reason,
    }


@router.post("/review/youtube-candidates/{candidate_id}/reject", response=ReviewActionOut)
def reject_youtube_candidate(request, candidate_id: int, payload: ReviewRejectIn):
    _require_review_auth(request)
    reason = _clean(payload.reason)
    candidate = _get_candidate(candidate_id)
    candidate.status = DiscoveredYoutubeVideo.Status.REJECTED
    candidate.raw_payload = {
        **candidate.raw_payload,
        "manual_review": {
            "action": "reject",
            "reason": reason,
            "reviewed_at": timezone.now().isoformat(),
        },
    }
    candidate.save(update_fields=["status", "raw_payload", "updated_at"])
    return {
        "candidate": _serialize_candidate(candidate),
        "result": "rejected",
        "reason": reason,
    }


def _require_review_auth(request) -> None:
    if not _is_authenticated(request):
        raise HttpError(401, "Review login required.")


def _is_authenticated(request) -> bool:
    return bool(request.session.get(SESSION_KEY))


def _get_candidate(candidate_id: int) -> DiscoveredYoutubeVideo:
    try:
        return DiscoveredYoutubeVideo.objects.get(id=candidate_id)
    except DiscoveredYoutubeVideo.DoesNotExist as exc:
        raise HttpError(404, "Candidate not found.") from exc


def _serialize_candidate(candidate: DiscoveredYoutubeVideo) -> dict:
    return {
        "id": candidate.id,
        "song_title": candidate.song_title,
        "artist_name": candidate.artist_name,
        "youtube_title": candidate.youtube_title,
        "youtube_url": candidate.youtube_url,
        "video_id": candidate.video_id,
        "channel_title": candidate.channel_title,
        "channel_id": candidate.channel_id,
        "uploaded_year": candidate.uploaded_year,
        "uploaded_month": candidate.uploaded_month,
        "official_score": candidate.official_score,
        "source_type": candidate.source_type,
        "status": candidate.status,
        "review_reason": _review_reason(candidate),
        "duration_seconds": _parse_int(candidate.raw_payload.get("duration_seconds")),
        "view_count": _parse_int(candidate.raw_payload.get("view_count")),
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }


def _review_reason(candidate: DiscoveredYoutubeVideo) -> str:
    review_payload = candidate.raw_payload.get("auto_promotion_review") or {}
    manual_payload = candidate.raw_payload.get("manual_review") or {}
    return review_payload.get("reason") or manual_payload.get("reason") or ""


def _parse_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clean(value: str) -> str:
    return " ".join((value or "").strip().split())[:255]
