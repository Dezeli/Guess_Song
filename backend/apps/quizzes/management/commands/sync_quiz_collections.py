import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.text import normalize_answer
from apps.quizzes.models import QuizAnswerAlias, QuizPack, QuizPackQuestion, QuizQuestion


YEAR_PACK_PREFIX = "연도별"
ARTIST_PACK_PREFIX = "가수별"
MIN_ARTIST_PACK_QUESTIONS = 5

LETTER_PRONUNCIATIONS = {
    "a": "에이",
    "b": "비",
    "c": "씨",
    "d": "디",
    "e": "이",
    "f": "에프",
    "g": "지",
    "h": "에이치",
    "i": "아이",
    "j": "제이",
    "k": "케이",
    "l": "엘",
    "m": "엠",
    "n": "엔",
    "o": "오",
    "p": "피",
    "q": "큐",
    "r": "알",
    "s": "에스",
    "t": "티",
    "u": "유",
    "v": "브이",
    "w": "더블유",
    "x": "엑스",
    "y": "와이",
    "z": "지",
}

ENGLISH_WORD_PRONUNCIATIONS = {
    "after": "애프터",
    "aespa": "에스파",
    "all": "올",
    "attention": "어텐션",
    "ateez": "에이티즈",
    "baby": "베이비",
    "bad": "배드",
    "beautiful": "뷰티풀",
    "better": "베터",
    "blue": "블루",
    "boy": "보이",
    "chill": "칠",
    "dance": "댄스",
    "dream": "드림",
    "easy": "이지",
    "feel": "필",
    "fire": "파이어",
    "flower": "플라워",
    "gaga": "가가",
    "girl": "걸",
    "good": "굿",
    "happy": "해피",
    "heart": "하트",
    "hello": "헬로",
    "hot": "핫",
    "how": "하우",
    "hype": "하입",
    "iu": "아이유",
    "ive": "아이브",
    "jeans": "진스",
    "kill": "킬",
    "kiss": "키스",
    "lady": "레이디",
    "life": "라이프",
    "like": "라이크",
    "love": "러브",
    "magic": "매직",
    "nct": "엔시티",
    "new": "뉴",
    "newjeans": "뉴진스",
    "nmixx": "엔믹스",
    "night": "나이트",
    "queen": "퀸",
    "queencard": "퀸카",
    "rhythm": "리듬",
    "riize": "라이즈",
    "rock": "락",
    "run": "런",
    "seventeen": "세븐틴",
    "shy": "샤이",
    "smile": "스마일",
    "smiley": "스마일리",
    "song": "송",
    "spot": "스팟",
    "star": "스타",
    "stay": "스테이",
    "stray": "스트레이",
    "super": "슈퍼",
    "sweet": "스위트",
    "tomboy": "톰보이",
    "walk": "워크",
    "way": "웨이",
    "what": "왓",
    "why": "와이",
    "you": "유",
}


class Command(BaseCommand):
    help = "Rebuild answer aliases and scoped quiz packs from approved questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-artist-questions",
            type=int,
            default=MIN_ARTIST_PACK_QUESTIONS,
            help="Minimum approved question count required to create an artist pack.",
        )

    def handle(self, *args, **options):
        min_artist_questions = max(options["min_artist_questions"], 1)
        questions = list(
            QuizQuestion.objects.filter(
                status=QuizQuestion.Status.APPROVED,
                song__approved=True,
                song__playable=True,
                song__blocked=False,
                youtube_source__status="approved",
            ).select_related("song__primary_artist")
        )

        with transaction.atomic():
            alias_counts = _sync_aliases(questions)
            year_pack_count, year_link_count = _sync_year_packs(questions)
            artist_pack_count, artist_link_count = _sync_artist_packs(
                questions,
                min_artist_questions=min_artist_questions,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Synced aliases title={title_aliases}, artist={artist_aliases}; "
                "year_packs={year_packs} year_links={year_links}; "
                "artist_packs={artist_packs} artist_links={artist_links}.".format(
                    **alias_counts,
                    year_packs=year_pack_count,
                    year_links=year_link_count,
                    artist_packs=artist_pack_count,
                    artist_links=artist_link_count,
                )
            )
        )


def _sync_aliases(questions: list[QuizQuestion]) -> dict[str, int]:
    counters = {"title_aliases": 0, "artist_aliases": 0}
    for question in questions:
        for alias in _title_aliases(question.answer_title):
            counters["title_aliases"] += _upsert_alias(
                question,
                QuizAnswerAlias.AnswerType.TITLE,
                alias,
            )
        for alias in _artist_aliases(question.answer_artist):
            counters["artist_aliases"] += _upsert_alias(
                question,
                QuizAnswerAlias.AnswerType.ARTIST,
                alias,
            )
    return counters


def _upsert_alias(question: QuizQuestion, answer_type: str, value: str) -> int:
    value = _clean(value)
    normalized_value = normalize_answer(value)
    if not value or not normalized_value:
        return 0

    alias, created = QuizAnswerAlias.objects.get_or_create(
        question=question,
        answer_type=answer_type,
        normalized_value=normalized_value,
        defaults={"value": value},
    )
    if not created and alias.value != value:
        alias.value = value
        alias.save(update_fields=["value"])
    return int(created)


def _title_aliases(title: str) -> tuple[str, ...]:
    aliases = [title]
    aliases.extend(_bracket_contents(title))
    aliases.append(_remove_bracketed_text(title))
    aliases.extend(_split_alias_parts(title))
    aliases.extend(_english_pronunciation_aliases(aliases))
    return _unique_clean_values(aliases)


def _artist_aliases(artist: str) -> tuple[str, ...]:
    aliases = [artist]
    aliases.extend(_bracket_contents(artist))
    aliases.append(_remove_bracketed_text(artist))
    aliases.extend(re.split(r"\s*[()/,&]\s*", artist or ""))
    aliases.extend(_english_pronunciation_aliases(aliases))
    return _unique_clean_values(aliases)


def _english_pronunciation_aliases(values: list[str]) -> list[str]:
    aliases = []
    for value in values:
        if not value or re.search(r"[가-힣]", value):
            continue
        words = re.findall(r"[A-Za-z]+", value)
        if not words:
            continue
        pronounced_words = [_pronounce_english_word(word) for word in words]
        if all(pronounced_words):
            aliases.append(" ".join(pronounced_words))
            aliases.append("".join(pronounced_words))
    return aliases


def _pronounce_english_word(word: str) -> str:
    lowered = word.lower()
    if lowered in ENGLISH_WORD_PRONUNCIATIONS:
        return ENGLISH_WORD_PRONUNCIATIONS[lowered]
    if word.isupper() and len(word) <= 6:
        return "".join(LETTER_PRONUNCIATIONS[letter] for letter in lowered)
    if len(lowered) <= 3 and not re.search(r"[aeiou]", lowered):
        return "".join(LETTER_PRONUNCIATIONS[letter] for letter in lowered)
    return ""


def _bracket_contents(value: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(r"[\[(（【]([^\]\)）】]+)[\])）】]", value or "")
        if match.group(1).strip()
    ]


def _remove_bracketed_text(value: str) -> str:
    return re.sub(r"\s*[\[(（【][^\]\)）】]+[\])）】]\s*", " ", value or "")


def _split_alias_parts(value: str) -> list[str]:
    parts = []
    for separator in ["/", "|"]:
        if separator in (value or ""):
            parts.extend(value.split(separator))
    return parts


def _unique_clean_values(values) -> tuple[str, ...]:
    seen = set()
    result = []
    for value in values:
        cleaned = _clean(value)
        normalized = normalize_answer(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)
    return tuple(result)


def _clean(value: str) -> str:
    return " ".join((value or "").strip().split())[:255]


def _sync_year_packs(questions: list[QuizQuestion]) -> tuple[int, int]:
    grouped = defaultdict(list)
    for question in questions:
        if question.song.release_year:
            grouped[question.song.release_year].append(question)

    pack_count = 0
    link_count = 0
    for year, year_questions in sorted(grouped.items(), reverse=True):
        pack, _ = QuizPack.objects.get_or_create(
            name=f"{YEAR_PACK_PREFIX} {year}",
            defaults={
                "description": f"{year}년에 공개된 곡으로 구성된 문제팩입니다.",
                "is_public": True,
            },
        )
        if not pack.is_public:
            pack.is_public = True
            pack.save(update_fields=["is_public"])
        pack_count += 1
        link_count += _replace_pack_links(pack, year_questions)

    return pack_count, link_count


def _sync_artist_packs(
    questions: list[QuizQuestion],
    min_artist_questions: int,
) -> tuple[int, int]:
    grouped = defaultdict(list)
    artist_names = {}
    for question in questions:
        artist = question.song.primary_artist
        grouped[artist.normalized_name].append(question)
        artist_names[artist.normalized_name] = artist.name

    pack_count = 0
    link_count = 0
    for artist_key, artist_questions in sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), artist_names[item[0]]),
    ):
        if len(artist_questions) < min_artist_questions:
            continue
        artist_name = artist_names[artist_key]
        pack, _ = QuizPack.objects.get_or_create(
            name=f"{ARTIST_PACK_PREFIX} {artist_name}",
            defaults={
                "description": f"{artist_name} 곡으로 구성된 문제팩입니다.",
                "is_public": True,
            },
        )
        if not pack.is_public:
            pack.is_public = True
            pack.save(update_fields=["is_public"])
        pack_count += 1
        link_count += _replace_pack_links(pack, artist_questions)

    return pack_count, link_count


def _replace_pack_links(pack: QuizPack, questions: list[QuizQuestion]) -> int:
    pack.pack_questions.all().delete()
    QuizPackQuestion.objects.bulk_create(
        [
            QuizPackQuestion(pack=pack, question=question, order=index)
            for index, question in enumerate(
                sorted(questions, key=lambda item: (item.answer_artist, item.answer_title, item.id)),
                start=1,
            )
        ]
    )
    return len(questions)
