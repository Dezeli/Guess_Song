from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Artist, Chart, ChartEntry, Track, TrackArtist, YouTubeCandidate
from apps.core.text import normalize_answer
from apps.quizzes.models import QuizAnswerAlias, QuizPack, QuizPackQuestion, QuizQuestion

SAMPLE_TRACKS = [
    {
        "rank": 1,
        "title": "LOVE DIVE",
        "artist": "IVE",
        "release_date": date(2022, 4, 5),
        "duration_ms": 177000,
        "isrc": "KRA382200001",
        "youtube_video_id": "Y8JFxS1HlDo",
        "youtube_title": "IVE 아이브 'LOVE DIVE' MV",
        "channel_title": "starshipTV",
        "start_time_seconds": 55,
        "difficulty": QuizQuestion.Difficulty.EASY,
        "aliases": ["LOVE DIVE", "러브 다이브", "아이브 러브 다이브"],
    },
    {
        "rank": 2,
        "title": "TOMBOY",
        "artist": "(G)I-DLE",
        "release_date": date(2022, 3, 14),
        "duration_ms": 174000,
        "isrc": "KRA382200002",
        "youtube_video_id": "Jh4QFaPmdss",
        "youtube_title": "(여자)아이들((G)I-DLE) - 'TOMBOY' Official Music Video",
        "channel_title": "(G)I-DLE (여자)아이들 (Official YouTube Channel)",
        "start_time_seconds": 48,
        "difficulty": QuizQuestion.Difficulty.EASY,
        "aliases": ["TOMBOY", "톰보이", "여자아이들 톰보이"],
    },
    {
        "rank": 3,
        "title": "Attention",
        "artist": "NewJeans",
        "release_date": date(2022, 8, 1),
        "duration_ms": 180000,
        "isrc": "KRA382200003",
        "youtube_video_id": "js1CtxSY38I",
        "youtube_title": "NewJeans (뉴진스) 'Attention' Official MV",
        "channel_title": "HYBE LABELS",
        "start_time_seconds": 43,
        "difficulty": QuizQuestion.Difficulty.EASY,
        "aliases": ["Attention", "어텐션", "뉴진스 어텐션"],
    },
    {
        "rank": 4,
        "title": "Hype Boy",
        "artist": "NewJeans",
        "release_date": date(2022, 8, 1),
        "duration_ms": 179000,
        "isrc": "KRA382200004",
        "youtube_video_id": "11cta61wi0g",
        "youtube_title": "NewJeans (뉴진스) 'Hype Boy' Official MV",
        "channel_title": "HYBE LABELS",
        "start_time_seconds": 44,
        "difficulty": QuizQuestion.Difficulty.EASY,
        "aliases": ["Hype Boy", "하입보이", "뉴진스 하입보이"],
    },
    {
        "rank": 5,
        "title": "After LIKE",
        "artist": "IVE",
        "release_date": date(2022, 8, 22),
        "duration_ms": 177000,
        "isrc": "KRA382200005",
        "youtube_video_id": "F0B7HDiY-10",
        "youtube_title": "IVE 아이브 'After LIKE' MV",
        "channel_title": "starshipTV",
        "start_time_seconds": 57,
        "difficulty": QuizQuestion.Difficulty.EASY,
        "aliases": ["After LIKE", "애프터 라이크", "아이브 애프터 라이크"],
    },
]


class Command(BaseCommand):
    help = "Seed sample quiz data for local development."

    @transaction.atomic
    def handle(self, *args, **options):
        chart, _ = Chart.objects.get_or_create(
            source=Chart.Source.CIRCLE,
            chart_type=Chart.ChartType.DIGITAL_YEARLY,
            year=2022,
            defaults={"name": "Circle Digital Chart 2022 Sample"},
        )
        pack, _ = QuizPack.objects.get_or_create(
            name="2022 K-POP Sample Pack",
            defaults={
                "description": "Local development sample pack based on 2022 chart-like data.",
                "is_public": True,
            },
        )

        created_questions = 0

        for index, item in enumerate(SAMPLE_TRACKS, start=1):
            artist, _ = Artist.objects.get_or_create(
                normalized_name=normalize_answer(item["artist"]),
                defaults={
                    "name": item["artist"],
                    "artist_type": Artist.ArtistType.GROUP,
                    "country": "KR",
                },
            )
            track, _ = Track.objects.get_or_create(
                isrc=item["isrc"],
                defaults={
                    "title": item["title"],
                    "normalized_title": normalize_answer(item["title"]),
                    "primary_artist": artist,
                    "release_date": item["release_date"],
                    "duration_ms": item["duration_ms"],
                },
            )
            TrackArtist.objects.get_or_create(
                track=track,
                artist=artist,
                role=TrackArtist.Role.PRIMARY,
                defaults={"order": 0},
            )
            chart_entry, _ = ChartEntry.objects.get_or_create(
                chart=chart,
                rank=item["rank"],
                defaults={
                    "title_raw": item["title"],
                    "artist_raw": item["artist"],
                    "track": track,
                },
            )
            candidate, _ = YouTubeCandidate.objects.get_or_create(
                video_id=item["youtube_video_id"],
                defaults={
                    "track": track,
                    "title": item["youtube_title"],
                    "channel_title": item["channel_title"],
                    "duration_seconds": item["duration_ms"] // 1000,
                    "official_score": 95,
                    "review_status": YouTubeCandidate.ReviewStatus.AUTO_APPROVED,
                },
            )
            question, question_created = QuizQuestion.objects.get_or_create(
                track=track,
                youtube_candidate=candidate,
                defaults={
                    "source_chart_entry": chart_entry,
                    "start_time_seconds": item["start_time_seconds"],
                    "play_duration_seconds": 20,
                    "answer_title": item["title"],
                    "answer_artist": item["artist"],
                    "difficulty": item["difficulty"],
                    "status": QuizQuestion.Status.APPROVED,
                },
            )
            created_questions += int(question_created)

            for alias in [item["title"], *item["aliases"]]:
                QuizAnswerAlias.objects.get_or_create(
                    question=question,
                    answer_type=QuizAnswerAlias.AnswerType.TITLE,
                    normalized_value=normalize_answer(alias),
                    defaults={"value": alias},
                )
            QuizAnswerAlias.objects.get_or_create(
                question=question,
                answer_type=QuizAnswerAlias.AnswerType.ARTIST,
                normalized_value=normalize_answer(item["artist"]),
                defaults={"value": item["artist"]},
            )

            QuizPackQuestion.objects.get_or_create(
                pack=pack,
                question=question,
                defaults={"order": index},
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(SAMPLE_TRACKS)} sample tracks, {created_questions} new questions."
            )
        )
