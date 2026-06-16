from django.db import models


class QuizPack(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class QuizQuestion(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        NORMAL = "normal", "Normal"
        HARD = "hard", "Hard"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        NEEDS_REVIEW = "needs_review", "Needs review"
        APPROVED = "approved", "Approved"
        DISABLED = "disabled", "Disabled"

    class PromptType(models.TextChoices):
        AUDIO = "audio", "Audio"

    song = models.ForeignKey("catalog.Song", on_delete=models.PROTECT, related_name="questions")
    youtube_source = models.ForeignKey(
        "catalog.YoutubeSource",
        on_delete=models.PROTECT,
        related_name="questions",
    )
    source_chart_entry = models.ForeignKey(
        "catalog.ChartEntry",
        on_delete=models.SET_NULL,
        related_name="questions",
        null=True,
        blank=True,
    )
    prompt_type = models.CharField(
        max_length=20,
        choices=PromptType.choices,
        default=PromptType.AUDIO,
    )
    start_time_seconds = models.PositiveSmallIntegerField(default=60)
    play_duration_seconds = models.PositiveSmallIntegerField(default=20)
    answer_title = models.CharField(max_length=255)
    answer_artist = models.CharField(max_length=255)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.answer_title} - {self.answer_artist}"


class QuizAnswerAlias(models.Model):
    class AnswerType(models.TextChoices):
        TITLE = "title", "Title"
        ARTIST = "artist", "Artist"
        FULL = "full", "Full"

    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="aliases")
    answer_type = models.CharField(max_length=20, choices=AnswerType.choices)
    value = models.CharField(max_length=255)
    normalized_value = models.CharField(max_length=255, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["question", "answer_type", "normalized_value"],
                name="unique_question_answer_alias",
            )
        ]

    def __str__(self) -> str:
        return self.value


class QuizPackQuestion(models.Model):
    pack = models.ForeignKey(QuizPack, on_delete=models.CASCADE, related_name="pack_questions")
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="question_packs",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["pack", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["pack", "question"], name="unique_pack_question")
        ]

    def __str__(self) -> str:
        return f"{self.pack} / {self.question}"
