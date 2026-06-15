from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.quizzes.models import QuizPack, QuizQuestion

from .models import Room


def room_group_name(code: str) -> str:
    return f"room_{code.upper()}"


def approved_question_count(pack: QuizPack) -> int:
    return QuizQuestion.objects.filter(
        question_packs__pack=pack,
        status=QuizQuestion.Status.APPROVED,
    ).count()


def get_room_for_state(code: str) -> Room:
    return (
        Room.objects.prefetch_related("participants", "game_session__rounds")
        .select_related("game_session__quiz_pack")
        .get(code=code.upper())
    )


def serialize_room(room: Room) -> dict:
    session = getattr(room, "game_session", None)
    pack = session.quiz_pack if session else None

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
