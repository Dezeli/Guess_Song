from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.quizzes.models import QuizPack, QuizQuestion

from .models import GameRound, Room


def room_group_name(code: str) -> str:
    return f"room_{code.upper()}"


def approved_question_count(pack: QuizPack) -> int:
    return QuizQuestion.objects.filter(
        question_packs__pack=pack,
        status=QuizQuestion.Status.APPROVED,
    ).count()


def get_room_for_state(code: str) -> Room:
    return (
        Room.objects.prefetch_related(
            "participants",
            "game_session__rounds__question__youtube_candidate",
        )
        .select_related("game_session__quiz_pack")
        .get(code=code.upper())
    )


def serialize_public_round(round_obj: GameRound | None) -> dict | None:
    if round_obj is None:
        return None

    question = round_obj.question
    candidate = question.youtube_candidate

    return {
        "round_id": round_obj.id,
        "round_index": round_obj.round_index,
        "question_id": question.id,
        "youtube_video_id": candidate.video_id,
        "start_time_seconds": question.start_time_seconds,
        "play_duration_seconds": question.play_duration_seconds,
        "difficulty": question.difficulty,
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
        "ended_at": round_obj.ended_at.isoformat() if round_obj.ended_at else None,
    }


def get_current_round(session) -> GameRound | None:
    if not session:
        return None

    rounds = list(session.rounds.all())
    for round_obj in rounds:
        if round_obj.round_index == session.current_round_index:
            return round_obj
    return None


def serialize_room(room: Room) -> dict:
    session = getattr(room, "game_session", None)
    pack = session.quiz_pack if session else None
    current_round = get_current_round(session)

    return {
        "code": room.code,
        "status": room.status,
        "quiz_pack": (
            {
                "id": pack.id,
                "name": pack.name,
                "approved_question_count": approved_question_count(pack),
            }
            if pack
            else None
        ),
        "game": (
            {
                "status": session.status,
                "current_round_index": session.current_round_index,
                "total_rounds": session.rounds.count(),
                "current_round": serialize_public_round(current_round),
            }
            if session
            else None
        ),
        "participants": [
            {
                "id": participant.id,
                "nickname": participant.nickname,
                "score": participant.score,
                "is_host": participant.is_host,
                "is_active": participant.is_active,
                "left_at": participant.left_at.isoformat() if participant.left_at else None,
            }
            for participant in room.participants.order_by("-is_host", "joined_at", "id")
        ],
        "settings": room.settings,
    }


def get_room_state(code: str) -> dict:
    return serialize_room(get_room_for_state(code))


def broadcast_room_state(code: str) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        room_group_name(code),
        {
            "type": "room.state",
            "room": get_room_state(code),
        },
    )


def broadcast_round_started(code: str, round_obj: GameRound) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        room_group_name(code),
        {
            "type": "round.started",
            "round": serialize_public_round(round_obj),
        },
    )
