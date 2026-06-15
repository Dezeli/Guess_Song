from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.quizzes.models import QuizPack, QuizQuestion

from .models import GameSession, Participant, Room
from .tokens import generate_room_code, generate_token

router = Router(tags=["rooms"])


class CreateRoomIn(Schema):
    quiz_pack_id: int
    host_nickname: str
    settings: dict = {}


class JoinRoomIn(Schema):
    nickname: str


class ParticipantOut(Schema):
    id: int
    nickname: str
    score: int
    is_host: bool


class QuizPackSummaryOut(Schema):
    id: int
    name: str
    approved_question_count: int


class RoomOut(Schema):
    code: str
    status: str
    quiz_pack: QuizPackSummaryOut | None
    participants: list[ParticipantOut]
    settings: dict


class CreateRoomOut(Schema):
    room: RoomOut
    host_token: str
    participant_token: str


class JoinRoomOut(Schema):
    room: RoomOut
    participant_token: str


def _clean_nickname(nickname: str) -> str:
    cleaned = " ".join(nickname.strip().split())
    if not cleaned:
        raise HttpError(400, "Nickname is required.")
    if len(cleaned) > 40:
        raise HttpError(400, "Nickname must be 40 characters or fewer.")
    return cleaned


def _approved_question_count(pack: QuizPack) -> int:
    return QuizQuestion.objects.filter(
        question_packs__pack=pack,
        status=QuizQuestion.Status.APPROVED,
    ).count()


def _serialize_room(room: Room) -> dict:
    session = getattr(room, "game_session", None)
    pack = session.quiz_pack if session else None

    return {
        "code": room.code,
        "status": room.status,
        "quiz_pack": (
            {
                "id": pack.id,
                "name": pack.name,
                "approved_question_count": _approved_question_count(pack),
            }
            if pack
            else None
        ),
        "participants": [
            {
                "id": participant.id,
                "nickname": participant.nickname,
                "score": participant.score,
                "is_host": participant.is_host,
            }
            for participant in room.participants.order_by("-is_host", "joined_at", "id")
        ],
        "settings": room.settings,
    }


@router.post("/rooms", response=CreateRoomOut)
def create_room(request, payload: CreateRoomIn):
    nickname = _clean_nickname(payload.host_nickname)
    quiz_pack = get_object_or_404(QuizPack, id=payload.quiz_pack_id, is_public=True)

    if _approved_question_count(quiz_pack) == 0:
        raise HttpError(400, "Quiz pack has no approved questions.")

    with transaction.atomic():
        room = Room.objects.create(
            code=generate_room_code(),
            host_token=generate_token("host"),
            settings=payload.settings,
        )
        participant = Participant.objects.create(
            room=room,
            nickname=nickname,
            session_token=generate_token("participant"),
            is_host=True,
        )
        GameSession.objects.create(
            room=room,
            quiz_pack=quiz_pack,
            settings=payload.settings,
        )

    return {
        "room": _serialize_room(room),
        "host_token": room.host_token,
        "participant_token": participant.session_token,
    }


@router.get("/rooms/{code}", response=RoomOut)
def get_room(request, code: str):
    room = get_object_or_404(
        Room.objects.prefetch_related("participants").select_related("game_session__quiz_pack"),
        code=code.upper(),
    )
    return _serialize_room(room)


@router.post("/rooms/{code}/join", response=JoinRoomOut)
def join_room(request, code: str, payload: JoinRoomIn):
    nickname = _clean_nickname(payload.nickname)
    room = get_object_or_404(Room, code=code.upper())

    if room.status != Room.Status.WAITING:
        raise HttpError(400, "Room is not joinable.")

    try:
        with transaction.atomic():
            participant = Participant.objects.create(
                room=room,
                nickname=nickname,
                session_token=generate_token("participant"),
            )
    except IntegrityError as exc:
        raise HttpError(409, "Nickname is already taken in this room.") from exc

    return {
        "room": _serialize_room(room),
        "participant_token": participant.session_token,
    }
