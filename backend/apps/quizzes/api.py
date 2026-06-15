from ninja import Router, Schema

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


@router.get("/quiz-packs", response=list[QuizPackListItem])
def list_quiz_packs(request):
    packs = QuizPack.objects.filter(is_public=True).prefetch_related("pack_questions__question")
    result = []

    for pack in packs:
        approved_count = sum(
            1
            for link in pack.pack_questions.all()
            if link.question.status == link.question.Status.APPROVED
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


@router.get("/quiz-packs/{pack_id}", response=QuizPackDetail)
def get_quiz_pack(request, pack_id: int):
    pack = QuizPack.objects.prefetch_related("pack_questions__question").get(
        id=pack_id,
        is_public=True,
    )
    questions = [
        {
            "id": link.question.id,
            "title": link.question.answer_title,
            "artist": link.question.answer_artist,
            "difficulty": link.question.difficulty,
            "play_duration_seconds": link.question.play_duration_seconds,
        }
        for link in pack.pack_questions.all()
        if link.question.status == link.question.Status.APPROVED
    ]

    return {
        "id": pack.id,
        "name": pack.name,
        "description": pack.description,
        "is_public": pack.is_public,
        "questions": questions,
    }
