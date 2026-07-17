from django.db.models import Count
from ninja import Router, Schema

from apps.catalog.models import Artist, Song, YoutubeSource

from .models import QuizPack

router = Router(tags=["quizzes"])


class QuizPackListItem(Schema):
    id: int
    name: str
    description: str
    is_public: bool
    approved_question_count: int


class QuizQuestionItem(Schema):
    id: int
    title: str
    artist: str
    difficulty: str
    play_duration_seconds: int


class QuizPackDetail(Schema):
    id: int
    name: str
    description: str
    is_public: bool
    questions: list[QuizQuestionItem]


class QuestionScopeOption(Schema):
    value: str
    label: str
    question_count: int


class QuestionScopeOptionsOut(Schema):
    years: list[QuestionScopeOption]
    artists: list[QuestionScopeOption]


@router.get("/quiz-packs", response=list[QuizPackListItem])
def list_quiz_packs(request):
    packs = QuizPack.objects.filter(is_public=True).prefetch_related(
        "pack_questions__question__song",
        "pack_questions__question__youtube_source",
    )
    result = []

    for pack in packs:
        approved_count = sum(
            1
            for link in pack.pack_questions.all()
            if _is_playable_approved_question(link.question)
        )
        result.append(
            {
                "id": pack.id,
                "name": pack.name,
                "description": pack.description,
                "is_public": pack.is_public,
                "approved_question_count": approved_count,
            }
        )

    return result


@router.get("/quiz-scopes", response=QuestionScopeOptionsOut)
def list_quiz_scopes(request):
    years = [
        {
            "value": str(item["release_year"]),
            "label": str(item["release_year"]),
            "question_count": item["question_count"],
        }
        for item in Song.objects.filter(
            questions__status="approved",
            approved=True,
            playable=True,
            blocked=False,
            questions__youtube_source__status=YoutubeSource.Status.APPROVED,
            release_year__isnull=False,
        )
        .values("release_year")
        .annotate(question_count=Count("questions", distinct=True))
        .order_by("-release_year")
    ]
    artists = [
        {
            "value": item["name"],
            "label": item["name"],
            "question_count": item["question_count"],
        }
        for item in Artist.objects.filter(
            songs__questions__status="approved",
            songs__approved=True,
            songs__playable=True,
            songs__blocked=False,
            songs__questions__youtube_source__status=YoutubeSource.Status.APPROVED,
        )
        .values("name")
        .annotate(question_count=Count("songs__questions", distinct=True))
        .filter(question_count__gt=0)
        .order_by("-question_count", "name")
    ]
    return {"years": years, "artists": artists}


@router.get("/quiz-packs/{pack_id}", response=QuizPackDetail)
def get_quiz_pack(request, pack_id: int):
    pack = QuizPack.objects.prefetch_related(
        "pack_questions__question__song",
        "pack_questions__question__youtube_source",
    ).get(id=pack_id, is_public=True)
    questions = [
        {
            "id": link.question.id,
            "title": link.question.answer_title,
            "artist": link.question.answer_artist,
            "difficulty": link.question.difficulty,
            "play_duration_seconds": link.question.play_duration_seconds,
        }
        for link in pack.pack_questions.all()
        if _is_playable_approved_question(link.question)
    ]

    return {
        "id": pack.id,
        "name": pack.name,
        "description": pack.description,
        "is_public": pack.is_public,
        "questions": questions,
    }


def _is_playable_approved_question(question) -> bool:
    return (
        question.status == question.Status.APPROVED
        and question.song.approved
        and question.song.playable
        and not question.song.blocked
        and question.youtube_source.status == YoutubeSource.Status.APPROVED
    )
