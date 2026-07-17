from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.catalog.models import YoutubeSource
from apps.quizzes.models import QuizPack, QuizQuestion

from .models import GameRound, Participant, Room, RoundAnswerFieldState


def room_group_name(code: str) -> str:
    return f"room_{code.upper()}"


def approved_question_count(pack: QuizPack) -> int:
    return QuizQuestion.objects.filter(
        question_packs__pack=pack,
        status=QuizQuestion.Status.APPROVED,
        song__approved=True,
        song__playable=True,
        song__blocked=False,
        youtube_source__status=YoutubeSource.Status.APPROVED,
    ).count()


def get_room_for_state(code: str) -> Room:
    return (
        Room.objects.prefetch_related(
            "participants",
            "teams",
            "game_session__rounds__answer_fields",
            "game_session__rounds__question__youtube_source",
            "game_session__rounds__question__song",
        )
        .select_related("game_session__quiz_pack")
        .get(code=code.upper())
    )


def serialize_public_round(round_obj: GameRound | None) -> dict | None:
    if round_obj is None:
        return None

    question = round_obj.question
    source = question.youtube_source

    skip_target_count = Participant.objects.filter(
        room=round_obj.session.room,
        status__in=[Participant.Status.ACTIVE, Participant.Status.AWAY],
    ).count()
    manual_skip_count = round_obj.skip_votes.filter(
        participant__status=Participant.Status.ACTIVE,
    ).count()
    away_skip_count = Participant.objects.filter(
        room=round_obj.session.room,
        status=Participant.Status.AWAY,
    ).count()
    answer_fields = _serialize_answer_fields(round_obj)

    return {
        "round_id": round_obj.id,
        "round_index": round_obj.round_index,
        "question_id": question.id,
        "youtube_video_id": source.video_id,
        "start_time_seconds": question.start_time_seconds,
        "play_duration_seconds": question.play_duration_seconds,
        "playback_segments": _playback_segments(round_obj),
        "difficulty": question.difficulty,
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
        "ended_at": round_obj.ended_at.isoformat() if round_obj.ended_at else None,
        "skip_count": min(manual_skip_count + away_skip_count, skip_target_count),
        "skip_target_count": skip_target_count,
        "answer_fields": answer_fields,
        "answer_submissions": _serialize_answer_submissions(round_obj),
    }


def _playback_segments(round_obj: GameRound) -> list[dict]:
    question = round_obj.question
    source = question.youtube_source
    total_play_seconds = int(
        round_obj.session.settings.get(
            "round_time_limit_sec",
            round_obj.session.room.settings.get("round_time_limit_sec", question.play_duration_seconds),
        )
    )
    segment_duration = max(total_play_seconds // 2, 1)
    first_start = question.start_time_seconds
    duration = source.duration_seconds
    if duration is None and question.song.duration_ms:
        duration = question.song.duration_ms // 1000
    second_start = first_start + max(segment_duration + 20, 30)

    if duration:
        latest_start = max(duration - segment_duration - 2, 0)
        if second_start > latest_start:
            second_start = max(first_start - segment_duration - 20, 0)
        if abs(second_start - first_start) < segment_duration + 5:
            second_start = min(latest_start, first_start + segment_duration + 5)

    return [
        {"start_time_seconds": first_start, "duration_seconds": segment_duration},
        {"start_time_seconds": max(second_start, 0), "duration_seconds": segment_duration},
    ]


def _serialize_answer_fields(round_obj: GameRound) -> list[dict]:
    configured_fields = ["title"]
    if round_obj.session.settings.get("answer_fields") == "TITLE_AND_ARTIST":
        configured_fields.append("artist")

    states = {state.field_type: state for state in round_obj.answer_fields.all()}
    payload = []
    for field_type in configured_fields:
        state = states.get(field_type)
        revealed_at = state.revealed_at if state else None
        answer = None
        if revealed_at:
            answer = (
                round_obj.question.answer_title
                if field_type == RoundAnswerFieldState.FieldType.TITLE
                else round_obj.question.answer_artist
            )

        payload.append(
            {
                "field_type": field_type,
                "is_open": not state.closed_at if state else True,
                "is_revealed": bool(revealed_at),
                "first_correct_at": (
                    state.first_correct_at.isoformat()
                    if state and state.first_correct_at
                    else None
                ),
                "closed_at": state.closed_at.isoformat() if state and state.closed_at else None,
                "revealed_at": revealed_at.isoformat() if revealed_at else None,
                "answer": answer,
            }
        )

    if "artist" not in configured_fields:
        title_state = states.get(RoundAnswerFieldState.FieldType.TITLE)
        reveal_artist = bool(round_obj.ended_at or (title_state and title_state.revealed_at))
        if reveal_artist:
            payload.append(
                {
                    "field_type": RoundAnswerFieldState.FieldType.ARTIST,
                    "is_open": False,
                    "is_revealed": True,
                    "first_correct_at": None,
                    "closed_at": round_obj.ended_at.isoformat() if round_obj.ended_at else None,
                    "revealed_at": (
                        round_obj.ended_at.isoformat()
                        if round_obj.ended_at
                        else title_state.revealed_at.isoformat()
                    ),
                    "answer": round_obj.question.answer_artist,
                }
            )

    return payload


def _serialize_answer_submissions(round_obj: GameRound) -> list[dict]:
    submissions = list(
        round_obj.submissions.select_related("participant")
        .order_by("-submitted_at", "-id")[:40]
    )
    payload = []
    previous_key = None
    previous_item = None
    for submission in reversed(submissions):
        key = (submission.participant_id, submission.answer_raw, submission.normalized_answer)
        if key == previous_key and previous_item:
            previous_item["id"] = max(previous_item["id"], submission.id)
            previous_item["is_correct"] = previous_item["is_correct"] or submission.is_correct
            previous_item["is_accepted"] = previous_item["is_accepted"] or submission.is_accepted
            previous_item["score_awarded"] += submission.score_awarded
            previous_item["submitted_at"] = submission.submitted_at.isoformat()
            continue
        item = {
            "id": submission.id,
            "participant_id": submission.participant_id,
            "nickname": submission.participant.nickname,
            "answer": submission.answer_raw,
            "is_correct": submission.is_correct,
            "is_accepted": submission.is_accepted,
            "score_awarded": submission.score_awarded,
            "submitted_at": submission.submitted_at.isoformat(),
        }
        previous_key = key
        previous_item = item
        payload.append(item)
    return payload[-20:]


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
        "title": room.title,
        "share_path": f"/rooms/{room.code}",
        "status": room.status,
        "server_time": timezone.now().isoformat(),
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
                "first_round_starts_at": (
                    session.first_round_starts_at.isoformat()
                    if session.first_round_starts_at
                    else None
                ),
            }
            if session
            else None
        ),
        "participants": [
            {
                "id": participant.id,
                "nickname": participant.nickname,
                "team_id": participant.team_id,
                "team_name": participant.team.name if participant.team else None,
                "score": participant.score,
                "is_host": participant.is_host,
                "status": participant.status,
                "left_at": participant.left_at.isoformat() if participant.left_at else None,
            }
            for participant in room.participants.select_related("team").order_by(
                "-is_host",
                "joined_at",
                "id",
            )
        ],
        "teams": [
            {
                "id": team.id,
                "name": team.name,
                "order": team.order,
                "score": team.score,
                "participant_count": team.participants.exclude(
                    status=Participant.Status.LEFT,
                ).count(),
            }
            for team in room.teams.order_by("order", "id")
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
