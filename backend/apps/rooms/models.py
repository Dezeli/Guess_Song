from django.db import models


class Room(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        PLAYING = "playing", "Playing"
        FINISHED = "finished", "Finished"
        CLOSED = "closed", "Closed"

    code = models.CharField(max_length=12, unique=True)
    host_token = models.CharField(max_length=128, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.code


class Participant(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    nickname = models.CharField(max_length=40)
    session_token = models.CharField(max_length=128, unique=True)
    score = models.IntegerField(default=0)
    is_host = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["room", "nickname"], name="unique_room_nickname")
        ]

    def __str__(self) -> str:
        return f"{self.nickname} ({self.room})"


class GameSession(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        PLAYING = "playing", "Playing"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="game_session")
    quiz_pack = models.ForeignKey(
        "quizzes.QuizPack",
        on_delete=models.SET_NULL,
        related_name="game_sessions",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    current_round_index = models.PositiveSmallIntegerField(default=0)
    settings = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"GameSession {self.room}"


class GameRound(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="rounds")
    question = models.ForeignKey(
        "quizzes.QuizQuestion",
        on_delete=models.PROTECT,
        related_name="rounds",
    )
    round_index = models.PositiveSmallIntegerField()
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["session", "round_index"]
        constraints = [
            models.UniqueConstraint(fields=["session", "round_index"], name="unique_session_round")
        ]

    def __str__(self) -> str:
        return f"{self.session} round {self.round_index}"


class AnswerSubmission(models.Model):
    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name="submissions")
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="answer_submissions",
    )
    answer_raw = models.CharField(max_length=255)
    normalized_answer = models.CharField(max_length=255, db_index=True)
    is_correct = models.BooleanField(default=False)
    score_awarded = models.IntegerField(default=0)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round", "submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["round", "participant"],
                name="unique_round_participant_submission",
            )
        ]

    def __str__(self) -> str:
        return f"{self.participant} / {self.answer_raw}"
