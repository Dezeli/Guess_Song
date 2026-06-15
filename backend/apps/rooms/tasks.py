from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import GameRound, GameSession, Room
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
            round_obj.ended_at = timezone.now()
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
                    args=[room.id, round_index],
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
