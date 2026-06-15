from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import GameRound, GameSession, Room, RoundAnswerFieldState
from .services import broadcast_room_state, broadcast_round_started


@shared_task
def start_round_task(room_id: int, round_index: int) -> None:
    should_schedule_end = False
    round_time_limit_sec = 0

    with transaction.atomic():
        room = Room.objects.select_for_update().get(id=room_id)
        if room.status != Room.Status.PLAYING:
            return

        session = GameSession.objects.select_for_update().get(room=room)
        if (
            session.status != GameSession.Status.PLAYING
            or session.current_round_index != round_index
        ):
            return

        round_obj = _get_locked_round(session, round_index)
        if round_obj is None or round_obj.ended_at:
            return

        if not round_obj.started_at:
            round_obj.started_at = timezone.now()
            round_obj.save(update_fields=["started_at"])
            _ensure_answer_field_states(round_obj)
            should_schedule_end = True
            round_time_limit_sec = int(
                session.settings.get(
                    "round_time_limit_sec",
                    room.settings.get("round_time_limit_sec", 20),
                )
            )

        transaction.on_commit(lambda: broadcast_round_started(room.code, round_obj))
        transaction.on_commit(lambda: broadcast_room_state(room.code))

        if should_schedule_end:
            transaction.on_commit(
                lambda: end_round_task.apply_async(
                    args=[room.id, round_index],
                    countdown=round_time_limit_sec,
                )
            )


@shared_task
def end_round_task(room_id: int, round_index: int) -> None:
    reveal_duration_sec = 0
    should_schedule_advance = False

    with transaction.atomic():
        room = Room.objects.select_for_update().get(id=room_id)
        if room.status != Room.Status.PLAYING:
            return

        session = GameSession.objects.select_for_update().get(room=room)
        if (
            session.status != GameSession.Status.PLAYING
            or session.current_round_index != round_index
        ):
            return

        round_obj = _get_locked_round(session, round_index)
        if round_obj is None or not round_obj.started_at:
            return

        if not round_obj.ended_at:
            now = timezone.now()
            round_obj.ended_at = now
            round_obj.save(update_fields=["ended_at"])
            _reveal_all_fields(round_obj, now)
            should_schedule_advance = True
            reveal_duration_sec = int(
                session.settings.get(
                    "reveal_duration_sec",
                    room.settings.get("reveal_duration_sec", 3),
                )
            )

        transaction.on_commit(lambda: broadcast_room_state(room.code))

        if should_schedule_advance:
            transaction.on_commit(
                lambda: advance_round_task.apply_async(
                    args=[room.id, round_index],
                    countdown=reveal_duration_sec,
                )
            )


@shared_task
def close_answer_field_task(round_id: int, field_type: str) -> None:
    should_schedule_advance = False
    reveal_duration_sec = 0
    room_id = None
    round_index = None

    with transaction.atomic():
        round_obj = (
            GameRound.objects.select_for_update()
            .select_related("session", "session__room", "question")
            .get(id=round_id)
        )
        session = round_obj.session
        room = session.room
        room_id = room.id
        round_index = round_obj.round_index

        if (
            room.status != Room.Status.PLAYING
            or session.status != GameSession.Status.PLAYING
            or session.current_round_index != round_obj.round_index
            or round_obj.ended_at
        ):
            return

        field_state = RoundAnswerFieldState.objects.select_for_update().filter(
            round=round_obj,
            field_type=field_type,
        ).first()
        if field_state is None:
            return

        now = timezone.now()
        if not field_state.closed_at:
            field_state.closed_at = now
        if not field_state.revealed_at:
            field_state.revealed_at = now
        field_state.save(update_fields=["closed_at", "revealed_at"])

        if _all_configured_fields_revealed(round_obj):
            round_obj.ended_at = now
            round_obj.save(update_fields=["ended_at"])
            should_schedule_advance = True
            reveal_duration_sec = int(
                session.settings.get(
                    "reveal_duration_sec",
                    room.settings.get("reveal_duration_sec", 3),
                )
            )

        transaction.on_commit(lambda: broadcast_room_state(room.code))

        if should_schedule_advance:
            transaction.on_commit(
                lambda: advance_round_task.apply_async(
                    args=[room_id, round_index],
                    countdown=reveal_duration_sec,
                )
            )


@shared_task
def advance_round_task(room_id: int, round_index: int) -> None:
    next_round_index: int | None = None

    with transaction.atomic():
        room = Room.objects.select_for_update().get(id=room_id)
        if room.status != Room.Status.PLAYING:
            return

        session = GameSession.objects.select_for_update().get(room=room)
        if (
            session.status != GameSession.Status.PLAYING
            or session.current_round_index != round_index
        ):
            return

        current_round = _get_locked_round(session, round_index)
        if current_round is None:
            return
        if not current_round.ended_at:
            current_round.ended_at = timezone.now()
            current_round.save(update_fields=["ended_at"])

        total_rounds = session.rounds.count()
        next_round_index = session.current_round_index + 1

        if next_round_index >= total_rounds:
            now = timezone.now()
            session.status = GameSession.Status.FINISHED
            session.finished_at = now
            session.save(update_fields=["status", "finished_at"])
            room.status = Room.Status.FINISHED
            room.save(update_fields=["status"])
            next_round_index = None
        else:
            session.current_round_index = next_round_index
            session.save(update_fields=["current_round_index"])

        transaction.on_commit(lambda: broadcast_room_state(room.code))

        if next_round_index is not None:
            transaction.on_commit(
                lambda: start_round_task.apply_async(args=[room.id, next_round_index])
            )


def _get_locked_round(session: GameSession, round_index: int) -> GameRound | None:
    return (
        session.rounds.select_for_update()
        .select_related("question", "question__youtube_candidate")
        .filter(round_index=round_index)
        .first()
    )


def _answer_fields_for_settings(settings: dict) -> list[str]:
    if settings.get("answer_fields") == "TITLE_AND_ARTIST":
        return [RoundAnswerFieldState.FieldType.TITLE, RoundAnswerFieldState.FieldType.ARTIST]
    return [RoundAnswerFieldState.FieldType.TITLE]


def _ensure_answer_field_states(round_obj: GameRound) -> None:
    for field_type in _answer_fields_for_settings(round_obj.session.settings):
        RoundAnswerFieldState.objects.get_or_create(round=round_obj, field_type=field_type)


def _reveal_all_fields(round_obj: GameRound, revealed_at) -> None:
    _ensure_answer_field_states(round_obj)
    RoundAnswerFieldState.objects.filter(
        round=round_obj,
        field_type__in=_answer_fields_for_settings(round_obj.session.settings),
        revealed_at__isnull=True,
    ).update(closed_at=revealed_at, revealed_at=revealed_at)


def _all_configured_fields_revealed(round_obj: GameRound) -> bool:
    configured_fields = _answer_fields_for_settings(round_obj.session.settings)
    return not RoundAnswerFieldState.objects.filter(
        round=round_obj,
        field_type__in=configured_fields,
        revealed_at__isnull=True,
    ).exists()
