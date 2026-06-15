from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.text import normalize_answer
from apps.quizzes.models import QuizAnswerAlias, QuizPack, QuizQuestion

from .models import AnswerSubmission, GameRound, GameSession, Participant, Room
from .services import (
    approved_question_count,
    broadcast_room_state,
    broadcast_round_started,
    serialize_public_round,
    serialize_room,
)
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
    is_active: bool
    left_at: str | None


class QuizPackSummaryOut(Schema):
    id: int
    name: str
    approved_question_count: int


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


def _get_current_round_or_400(session: GameSession) -> GameRound:
    round_obj = session.rounds.select_related(
        "question",
        "question__youtube_candidate",
    ).filter(round_index=session.current_round_index).first()

    if not round_obj:
        raise HttpError(400, "Current round does not exist.")
    return round_obj


def _is_correct_answer(question: QuizQuestion, normalized_answer: str) -> bool:
    return QuizAnswerAlias.objects.filter(
        question=question,
        normalized_value=normalized_answer,
    ).exists()


def _score_answer(is_correct: bool) -> int:
    return 100 if is_correct else 0


@router.post("/rooms", response=CreateRoomOut)
def create_room(request, payload: CreateRoomIn):
    nickname = _clean_nickname(payload.host_nickname)
    quiz_pack = get_object_or_404(QuizPack, id=payload.quiz_pack_id, is_public=True)

    if approved_question_count(quiz_pack) == 0:
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

    if room.status != Room.Status.WAITING:
        raise HttpError(400, "Room is not joinable.")

    try:
        with transaction.atomic():
            participant = Participant.objects.create(
                room=room,
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

        if participant.is_active:
            participant.is_active = False
            participant.left_at = timezone.now()
            participant.save(update_fields=["is_active", "left_at"])

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

        room.status = Room.Status.PLAYING
        room.save(update_fields=["status"])

        session.status = GameSession.Status.PLAYING
        session.current_round_index = 0
        session.save(update_fields=["status", "current_round_index"])

        GameRound.objects.bulk_create(
            [
                GameRound(session=session, question=question, round_index=index)
                for index, question in enumerate(selected_questions)
            ]
        )
        transaction.on_commit(lambda: broadcast_room_state(room.code))

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
        participant = _require_participant(request, room)

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
        is_correct = _is_correct_answer(round_obj.question, normalized_answer)
        score_awarded = _score_answer(is_correct)

        try:
            submission = AnswerSubmission.objects.create(
                round=round_obj,
                participant=participant,
                answer_raw=answer,
                normalized_answer=normalized_answer,
                is_correct=is_correct,
                score_awarded=score_awarded,
            )
        except IntegrityError as exc:
            raise HttpError(409, "Participant has already submitted an answer for this round.") from exc

        if submission.score_awarded:
            participant.score += submission.score_awarded
            participant.save(update_fields=["score"])

        transaction.on_commit(lambda: broadcast_room_state(room.code))

    return {
        "is_correct": is_correct,
        "score_awarded": score_awarded,
        "total_score": participant.score,
    }
