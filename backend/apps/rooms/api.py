from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.text import normalize_answer
from apps.quizzes.models import QuizAnswerAlias, QuizPack, QuizQuestion

from .game_settings import normalize_room_settings
from .models import (
    AnswerSubmission,
    GameRound,
    GameSession,
    Participant,
    Room,
    RoomTeam,
    RoundAnswerFieldState,
    RoundSkipVote,
)
from .services import (
    approved_question_count,
    broadcast_room_state,
    broadcast_round_started,
    serialize_public_round,
    serialize_room,
)
from .tasks import advance_round_task, close_answer_field_task, end_round_task, start_round_task
from .tokens import generate_room_code, generate_token

router = Router(tags=["rooms"])


class CreateRoomIn(Schema):
    quiz_pack_id: int
    host_nickname: str
    settings: dict | None = None


class JoinRoomIn(Schema):
    nickname: str
    team_id: int | None = None


class ParticipantOut(Schema):
    id: int
    nickname: str
    team_id: int | None
    team_name: str | None
    score: int
    is_host: bool
    status: str
    left_at: str | None


class QuizPackSummaryOut(Schema):
    id: int
    name: str
    approved_question_count: int


class RoomTeamOut(Schema):
    id: int
    name: str
    order: int
    score: int
    participant_count: int


class CurrentRoundOut(Schema):
    round_id: int
    round_index: int
    question_id: int
    youtube_video_id: str
    start_time_seconds: int
    play_duration_seconds: int
    difficulty: str
    started_at: str | None
    ended_at: str | None
    skip_count: int
    skip_target_count: int
    answer_fields: list[dict]


class GameStateOut(Schema):
    status: str
    current_round_index: int
    total_rounds: int
    current_round: CurrentRoundOut | None


class RoomOut(Schema):
    code: str
    status: str
    quiz_pack: QuizPackSummaryOut | None
    game: GameStateOut | None
    participants: list[ParticipantOut]
    teams: list[RoomTeamOut]
    settings: dict


class CreateRoomOut(Schema):
    room: RoomOut
    host_token: str
    participant_token: str


class JoinRoomOut(Schema):
    room: RoomOut
    participant_token: str


class LeaveRoomOut(Schema):
    room: RoomOut


class ParticipantStatusOut(Schema):
    room: RoomOut


class StartGameOut(Schema):
    room: RoomOut


class RoundStartedOut(Schema):
    round: CurrentRoundOut


class NextRoundOut(Schema):
    room: RoomOut


class SubmitAnswerIn(Schema):
    answer: str


class SubmitAnswerOut(Schema):
    is_correct: bool
    score_awarded: int
    total_score: int
    matched_fields: list[str]


class SkipRoundOut(Schema):
    room: RoomOut


def _clean_nickname(nickname: str) -> str:
    cleaned = " ".join(nickname.strip().split())
    if not cleaned:
        raise HttpError(400, "Nickname is required.")
    if len(cleaned) > 40:
        raise HttpError(400, "Nickname must be 40 characters or fewer.")
    return cleaned


def _get_question_count(settings: dict, approved_count: int) -> int:
    raw_count = settings.get("question_count", approved_count)

    try:
        requested_count = int(raw_count)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, "question_count must be a number.") from exc

    if requested_count <= 0:
        raise HttpError(400, "question_count must be greater than zero.")

    return min(requested_count, approved_count)


def _require_host(request, room: Room) -> None:
    host_token = request.headers.get("X-Host-Token")

    if not host_token:
        raise HttpError(401, "X-Host-Token header is required.")
    if not room.host_token or host_token != room.host_token:
        raise HttpError(403, "Invalid host token.")


def _require_participant(request, room: Room) -> Participant:
    participant_token = request.headers.get("X-Participant-Token")

    if not participant_token:
        raise HttpError(401, "X-Participant-Token header is required.")

    participant = Participant.objects.filter(
        room=room,
        session_token=participant_token,
    ).first()
    if not participant:
        raise HttpError(403, "Invalid participant token.")
    return participant


def _require_active_participant(request, room: Room) -> Participant:
    participant = _require_participant(request, room)
    if participant.status != Participant.Status.ACTIVE:
        raise HttpError(403, "Participant is not active.")
    return participant


def _is_room_joinable(room: Room) -> bool:
    if room.status == Room.Status.WAITING:
        return True
    if room.status == Room.Status.PLAYING:
        return bool(room.settings.get("allow_late_join", True))
    return False


def _get_current_round_or_400(session: GameSession) -> GameRound:
    round_obj = session.rounds.select_related(
        "question",
        "question__youtube_candidate",
    ).filter(round_index=session.current_round_index).first()

    if not round_obj:
        raise HttpError(400, "Current round does not exist.")
    return round_obj


def _answer_matches_field(question: QuizQuestion, field_type: str, normalized_answer: str) -> bool:
    fallback_value = (
        question.answer_title
        if field_type == RoundAnswerFieldState.FieldType.TITLE
        else question.answer_artist
    )
    if normalize_answer(fallback_value) == normalized_answer:
        return True

    return QuizAnswerAlias.objects.filter(
        question=question,
        answer_type=field_type,
        normalized_value=normalized_answer,
    ).exists()


def _answer_fields_for_settings(settings: dict) -> list[str]:
    if settings.get("answer_fields") == "TITLE_AND_ARTIST":
        return [RoundAnswerFieldState.FieldType.TITLE, RoundAnswerFieldState.FieldType.ARTIST]
    return [RoundAnswerFieldState.FieldType.TITLE]


def _get_or_create_field_state(
    round_obj: GameRound,
    field_type: str,
) -> RoundAnswerFieldState:
    field_state, _ = RoundAnswerFieldState.objects.select_for_update().get_or_create(
        round=round_obj,
        field_type=field_type,
    )
    return field_state


def _is_field_open_for_acceptance(
    field_state: RoundAnswerFieldState,
    answer_limit_mode: str,
    now,
) -> bool:
    if field_state.closed_at:
        return False

    if answer_limit_mode == "FIVE_SECONDS" and field_state.first_correct_at:
        if now - field_state.first_correct_at > timedelta(seconds=5):
            field_state.closed_at = field_state.first_correct_at + timedelta(seconds=5)
            field_state.revealed_at = field_state.closed_at
            field_state.save(update_fields=["closed_at", "revealed_at"])
            return False

    return True


def _participant_already_accepted(
    round_obj: GameRound,
    participant: Participant,
    field_type: str,
) -> bool:
    return AnswerSubmission.objects.filter(
        round=round_obj,
        participant=participant,
        answer_type=field_type,
        is_accepted=True,
    ).exists()


def _accepted_count(round_obj: GameRound, field_type: str) -> int:
    return (
        AnswerSubmission.objects.filter(
            round=round_obj,
            answer_type=field_type,
            is_accepted=True,
        )
        .values("participant_id")
        .distinct()
        .count()
    )


def _team_already_awarded(round_obj: GameRound, team: RoomTeam, field_type: str) -> bool:
    return AnswerSubmission.objects.filter(
        round=round_obj,
        participant__team=team,
        answer_type=field_type,
        score_awarded__gt=0,
    ).exists()


def _award_score(
    room: Room,
    participant: Participant,
    round_obj: GameRound,
    field_type: str,
) -> int:
    if room.settings.get("play_mode") == "TEAM":
        if not participant.team_id:
            return 0
        team = RoomTeam.objects.select_for_update().get(id=participant.team_id)
        if _team_already_awarded(round_obj, team, field_type):
            return 0
        team.score += 1
        team.save(update_fields=["score"])
        return 1

    participant.score += 1
    participant.save(update_fields=["score"])
    return 1


def _active_skip_target_count(room: Room) -> int:
    return Participant.objects.filter(
        room=room,
        status__in=[Participant.Status.ACTIVE, Participant.Status.AWAY],
    ).count()


def _current_skip_count(round_obj: GameRound) -> int:
    room = round_obj.session.room
    manual_skip_count = round_obj.skip_votes.filter(
        participant__status=Participant.Status.ACTIVE,
    ).count()
    away_skip_count = Participant.objects.filter(
        room=room,
        status=Participant.Status.AWAY,
    ).count()
    return min(manual_skip_count + away_skip_count, _active_skip_target_count(room))


def _schedule_round_end(room: Room, round_obj: GameRound) -> None:
    transaction.on_commit(
        lambda: end_round_task.apply_async(args=[room.id, round_obj.round_index])
    )


def _schedule_answer_field_close(round_obj: GameRound, field_type: str) -> None:
    transaction.on_commit(
        lambda: close_answer_field_task.apply_async(
            args=[round_obj.id, field_type],
            countdown=5,
        )
    )


def _configured_field_states_revealed(round_obj: GameRound, settings: dict) -> bool:
    configured_fields = _answer_fields_for_settings(settings)
    return not RoundAnswerFieldState.objects.filter(
        round=round_obj,
        field_type__in=configured_fields,
        revealed_at__isnull=True,
    ).exists()


def _schedule_advance_after_reveal(room: Room, session: GameSession, round_obj: GameRound) -> None:
    reveal_duration_sec = int(
        session.settings.get(
            "reveal_duration_sec",
            room.settings.get("reveal_duration_sec", 3),
        )
    )
    transaction.on_commit(
        lambda: advance_round_task.apply_async(
            args=[room.id, round_obj.round_index],
            countdown=reveal_duration_sec,
        )
    )


def _create_room_teams(room: Room, settings: dict) -> None:
    if settings.get("play_mode") != "TEAM":
        return

    for index in range(int(settings.get("team_count", 2))):
        RoomTeam.objects.create(room=room, name=f"Team {index + 1}", order=index + 1)


def _get_join_team(room: Room, settings: dict, team_id: int | None) -> RoomTeam | None:
    if settings.get("play_mode") != "TEAM":
        return None

    if settings.get("team_assign_mode") == "RANDOM":
        return None

    if team_id is None:
        raise HttpError(400, "team_id is required for team self-select rooms.")

    team = RoomTeam.objects.filter(room=room, id=team_id).first()
    if not team:
        raise HttpError(400, "Invalid team_id for this room.")
    return team


def _assign_random_teams(room: Room) -> None:
    if room.settings.get("play_mode") != "TEAM":
        return
    if room.settings.get("team_assign_mode") != "RANDOM":
        return

    teams = list(room.teams.order_by("order", "id"))
    if not teams:
        return

    participants = list(
        room.participants.filter(team__isnull=True)
        .exclude(status=Participant.Status.LEFT)
        .order_by("id")
    )
    for participant in participants:
        team = min(
            teams,
            key=lambda candidate: candidate.participants.exclude(
                status=Participant.Status.LEFT,
            ).count(),
        )
        participant.team = team
        participant.save(update_fields=["team"])


@router.post("/rooms", response=CreateRoomOut)
def create_room(request, payload: CreateRoomIn):
    nickname = _clean_nickname(payload.host_nickname)
    quiz_pack = get_object_or_404(QuizPack, id=payload.quiz_pack_id, is_public=True)
    settings = normalize_room_settings(payload.settings)

    if approved_question_count(quiz_pack) == 0:
        raise HttpError(400, "Quiz pack has no approved questions.")

    with transaction.atomic():
        room = Room.objects.create(
            code=generate_room_code(),
            host_token=generate_token("host"),
            settings=settings,
        )
        _create_room_teams(room, settings)
        host_team = None
        if (
            settings.get("play_mode") == "TEAM"
            and settings.get("team_assign_mode") == "SELF_SELECT"
        ):
            host_team = room.teams.order_by("order", "id").first()
        participant = Participant.objects.create(
            room=room,
            team=host_team,
            nickname=nickname,
            session_token=generate_token("participant"),
            is_host=True,
        )
        GameSession.objects.create(
            room=room,
            quiz_pack=quiz_pack,
            settings=settings,
        )

    return {
        "room": serialize_room(room),
        "host_token": room.host_token,
        "participant_token": participant.session_token,
    }


@router.get("/rooms/{code}", response=RoomOut)
def get_room(request, code: str):
    room = get_object_or_404(
        Room.objects.prefetch_related("participants").select_related("game_session__quiz_pack"),
        code=code.upper(),
    )
    return serialize_room(room)


@router.post("/rooms/{code}/join", response=JoinRoomOut)
def join_room(request, code: str, payload: JoinRoomIn):
    nickname = _clean_nickname(payload.nickname)
    room = get_object_or_404(Room, code=code.upper())

    if not _is_room_joinable(room):
        raise HttpError(400, "Room is not joinable.")
    team = _get_join_team(room, room.settings, payload.team_id)

    try:
        with transaction.atomic():
            participant = Participant.objects.create(
                room=room,
                team=team,
                nickname=nickname,
                session_token=generate_token("participant"),
            )
            transaction.on_commit(lambda: broadcast_room_state(room.code))
    except IntegrityError as exc:
        raise HttpError(409, "Nickname is already taken in this room.") from exc

    return {
        "room": serialize_room(room),
        "participant_token": participant.session_token,
    }


@router.post("/rooms/{code}/leave", response=LeaveRoomOut)
def leave_room(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        participant = _require_participant(request, room)

        if participant.status != Participant.Status.LEFT:
            participant.status = Participant.Status.LEFT
            participant.is_active = False
            participant.left_at = timezone.now()
            participant.save(update_fields=["status", "is_active", "left_at"])

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    room = Room.objects.prefetch_related(
        "participants",
        "game_session__rounds__question__youtube_candidate",
    ).select_related("game_session__quiz_pack").get(id=room.id)

    return {"room": serialize_room(room)}


@router.post("/rooms/{code}/away", response=ParticipantStatusOut)
def set_participant_away(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        participant = _require_participant(request, room)

        if participant.status == Participant.Status.LEFT:
            raise HttpError(400, "Left participants cannot become away.")

        if participant.status != Participant.Status.AWAY:
            participant.status = Participant.Status.AWAY
            participant.is_active = True
            participant.save(update_fields=["status", "is_active"])

        if room.status == Room.Status.PLAYING:
            session = GameSession.objects.select_for_update().get(room=room)
            if session.status == GameSession.Status.PLAYING:
                round_obj = _get_current_round_or_400(session)
                if round_obj.started_at and not round_obj.ended_at:
                    if _current_skip_count(round_obj) >= _active_skip_target_count(room):
                        _schedule_round_end(room, round_obj)

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    room = Room.objects.prefetch_related(
        "participants",
        "game_session__rounds__question__youtube_candidate",
    ).select_related("game_session__quiz_pack").get(id=room.id)

    return {"room": serialize_room(room)}


@router.post("/rooms/{code}/active", response=ParticipantStatusOut)
def set_participant_active(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        participant = _require_participant(request, room)

        if participant.status == Participant.Status.LEFT:
            raise HttpError(400, "Left participants cannot become active.")

        if participant.status != Participant.Status.ACTIVE:
            participant.status = Participant.Status.ACTIVE
            participant.is_active = True
            participant.save(update_fields=["status", "is_active"])

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    room = Room.objects.prefetch_related(
        "participants",
        "game_session__rounds__question__youtube_candidate",
    ).select_related("game_session__quiz_pack").get(id=room.id)

    return {"room": serialize_room(room)}


@router.post("/rooms/{code}/start", response=StartGameOut)
def start_game(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(
            Room.objects.select_for_update(),
            code=code.upper(),
        )
        _require_host(request, room)

        if room.status != Room.Status.WAITING:
            raise HttpError(400, "Room has already started or is not startable.")

        session = GameSession.objects.select_related("quiz_pack").get(room=room)
        quiz_pack = session.quiz_pack

        if not quiz_pack:
            raise HttpError(400, "Room has no quiz pack.")

        approved_questions = list(
            QuizQuestion.objects.filter(
                question_packs__pack=quiz_pack,
                status=QuizQuestion.Status.APPROVED,
            )
            .order_by("question_packs__order", "id")
            .distinct()
        )

        question_count = _get_question_count(room.settings, len(approved_questions))
        if not approved_questions:
            raise HttpError(400, "Quiz pack has no approved questions.")

        selected_questions = approved_questions[:question_count]
        _assign_random_teams(room)

        room.status = Room.Status.PLAYING
        room.save(update_fields=["status"])

        session.status = GameSession.Status.PLAYING
        session.current_round_index = 0
        session.started_at = timezone.now()
        session.save(update_fields=["status", "current_round_index", "started_at"])

        GameRound.objects.bulk_create(
            [
                GameRound(session=session, question=question, round_index=index)
                for index, question in enumerate(selected_questions)
            ]
        )
        countdown_sec = int(room.settings.get("countdown_sec", 3))
        transaction.on_commit(lambda: broadcast_room_state(room.code))
        transaction.on_commit(
            lambda: start_round_task.apply_async(
                args=[room.id, 0],
                countdown=countdown_sec,
            )
        )

    room = Room.objects.prefetch_related("participants", "game_session__rounds").select_related(
        "game_session__quiz_pack"
    ).get(id=room.id)

    return {"room": serialize_room(room)}


@router.post("/rooms/{code}/rounds/current/start", response=RoundStartedOut)
def start_current_round(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        _require_host(request, room)

        if room.status != Room.Status.PLAYING:
            raise HttpError(400, "Room is not playing.")

        session = GameSession.objects.select_for_update().get(room=room)
        if session.status != GameSession.Status.PLAYING:
            raise HttpError(400, "Game session is not playing.")

        round_obj = _get_current_round_or_400(session)
        if round_obj.ended_at:
            raise HttpError(400, "Current round has already ended.")

        if not round_obj.started_at:
            round_obj.started_at = timezone.now()
            round_obj.save(update_fields=["started_at"])

        transaction.on_commit(lambda: broadcast_round_started(room.code, round_obj))

    return {"round": serialize_public_round(round_obj)}


@router.post("/rooms/{code}/rounds/next", response=NextRoundOut)
def move_to_next_round(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        _require_host(request, room)

        if room.status != Room.Status.PLAYING:
            raise HttpError(400, "Room is not playing.")

        session = GameSession.objects.select_for_update().get(room=room)
        if session.status != GameSession.Status.PLAYING:
            raise HttpError(400, "Game session is not playing.")

        current_round = _get_current_round_or_400(session)
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
        else:
            session.current_round_index = next_round_index
            session.save(update_fields=["current_round_index"])

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    room = Room.objects.prefetch_related(
        "participants",
        "game_session__rounds__question__youtube_candidate",
    ).select_related("game_session__quiz_pack").get(id=room.id)

    return {"room": serialize_room(room)}


@router.post("/rooms/{code}/rounds/current/answers", response=SubmitAnswerOut)
def submit_current_round_answer(request, code: str, payload: SubmitAnswerIn):
    answer = payload.answer.strip()
    if not answer:
        raise HttpError(400, "Answer is required.")

    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        participant = _require_active_participant(request, room)

        if room.status != Room.Status.PLAYING:
            raise HttpError(400, "Room is not playing.")

        session = GameSession.objects.select_for_update().get(room=room)
        if session.status != GameSession.Status.PLAYING:
            raise HttpError(400, "Game session is not playing.")

        round_obj = _get_current_round_or_400(session)
        if not round_obj.started_at:
            raise HttpError(400, "Current round has not started.")
        if round_obj.ended_at:
            raise HttpError(400, "Current round has already ended.")

        normalized_answer = normalize_answer(answer)
        answer_limit_mode = room.settings.get("answer_limit_mode", "FIVE_SECONDS")
        answer_fields = _answer_fields_for_settings(room.settings)
        now = timezone.now()
        score_awarded = 0
        matched_fields: list[str] = []
        is_correct = False
        total_score = participant.team.score if participant.team else participant.score
        for field_type in answer_fields:
            _get_or_create_field_state(round_obj, field_type)

        for field_type in answer_fields:
            field_state = _get_or_create_field_state(round_obj, field_type)
            field_correct = _answer_matches_field(round_obj.question, field_type, normalized_answer)
            field_accepted = False
            field_score_awarded = 0

            if field_correct:
                is_correct = True

            if (
                field_correct
                and _is_field_open_for_acceptance(field_state, answer_limit_mode, now)
                and not _participant_already_accepted(round_obj, participant, field_type)
            ):
                if answer_limit_mode == "FIRST_ONLY" and field_state.first_correct_at:
                    field_accepted = False
                else:
                    field_accepted = True
                    matched_fields.append(field_type)
                    field_score_awarded = _award_score(room, participant, round_obj, field_type)
                    score_awarded += field_score_awarded
                    if room.settings.get("play_mode") == "TEAM" and participant.team_id:
                        participant.team.refresh_from_db(fields=["score"])
                        total_score = participant.team.score
                    else:
                        total_score = participant.score

                    if not field_state.first_correct_at:
                        field_state.first_correct_at = now
                        if answer_limit_mode == "FIVE_SECONDS":
                            _schedule_answer_field_close(round_obj, field_type)

                    if answer_limit_mode == "FIRST_ONLY":
                        field_state.closed_at = now
                        field_state.revealed_at = now
                    elif answer_limit_mode == "ALL_CORRECT":
                        target_count = Participant.objects.filter(
                            room=room,
                            status=Participant.Status.ACTIVE,
                        ).count()
                        if _accepted_count(round_obj, field_type) + 1 >= target_count:
                            field_state.closed_at = now
                            field_state.revealed_at = now

                    field_state.save(update_fields=["first_correct_at", "closed_at", "revealed_at"])

                    if (
                        field_state.revealed_at
                        and _configured_field_states_revealed(round_obj, room.settings)
                        and not round_obj.ended_at
                    ):
                        round_obj.ended_at = now
                        round_obj.save(update_fields=["ended_at"])
                        _schedule_advance_after_reveal(room, session, round_obj)

            AnswerSubmission.objects.create(
                round=round_obj,
                participant=participant,
                answer_raw=answer,
                answer_type=field_type,
                normalized_answer=normalized_answer,
                is_correct=field_correct,
                is_accepted=field_accepted,
                score_awarded=field_score_awarded,
            )

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    return {
        "is_correct": is_correct,
        "score_awarded": score_awarded,
        "total_score": total_score,
        "matched_fields": matched_fields,
    }


@router.post("/rooms/{code}/rounds/current/skip", response=SkipRoundOut)
def skip_current_round(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        participant = _require_participant(request, room)

        if participant.status == Participant.Status.LEFT:
            raise HttpError(403, "Left participants cannot vote to skip.")

        if room.status != Room.Status.PLAYING:
            raise HttpError(400, "Room is not playing.")

        session = GameSession.objects.select_for_update().get(room=room)
        if session.status != GameSession.Status.PLAYING:
            raise HttpError(400, "Game session is not playing.")

        round_obj = _get_current_round_or_400(session)
        if not round_obj.started_at:
            raise HttpError(400, "Current round has not started.")
        if round_obj.ended_at:
            raise HttpError(400, "Current round has already ended.")

        if participant.status == Participant.Status.ACTIVE:
            try:
                RoundSkipVote.objects.create(round=round_obj, participant=participant)
            except IntegrityError:
                pass

        if _current_skip_count(round_obj) >= _active_skip_target_count(room):
            _schedule_round_end(room, round_obj)

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    room = Room.objects.prefetch_related(
        "participants",
        "game_session__rounds__question__youtube_candidate",
    ).select_related("game_session__quiz_pack").get(id=room.id)

    return {"room": serialize_room(room)}


@router.post("/rooms/{code}/rounds/current/force-skip", response=SkipRoundOut)
def force_skip_current_round(request, code: str):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), code=code.upper())
        _require_host(request, room)

        if room.status != Room.Status.PLAYING:
            raise HttpError(400, "Room is not playing.")

        session = GameSession.objects.select_for_update().get(room=room)
        if session.status != GameSession.Status.PLAYING:
            raise HttpError(400, "Game session is not playing.")

        round_obj = _get_current_round_or_400(session)
        if not round_obj.started_at:
            raise HttpError(400, "Current round has not started.")
        if round_obj.ended_at:
            raise HttpError(400, "Current round has already ended.")

        _schedule_round_end(room, round_obj)
        transaction.on_commit(lambda: broadcast_room_state(room.code))

    room = Room.objects.prefetch_related(
        "participants",
        "game_session__rounds__question__youtube_candidate",
    ).select_related("game_session__quiz_pack").get(id=room.id)

    return {"room": serialize_room(room)}
