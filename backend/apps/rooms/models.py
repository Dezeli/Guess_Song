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
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        AWAY = "AWAY", "Away"
        LEFT = "LEFT", "Left"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    nickname = models.CharField(max_length=40)
    session_token = models.CharField(max_length=128, unique=True)
    score = models.IntegerField(default=0)
    is_host = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
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


class RoundSkipVote(models.Model):
    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name="skip_votes")
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="round_skip_votes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["round", "participant"],
                name="unique_round_participant_skip_vote",
            )
        ]

    def __str__(self) -> str:
        return f"{self.participant} skip / {self.round}"


class RoundAnswerFieldState(models.Model):
    class FieldType(models.TextChoices):
        TITLE = "title", "Title"
        ARTIST = "artist", "Artist"

    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name="answer_fields")
    field_type = models.CharField(max_length=20, choices=FieldType.choices)
    first_correct_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    revealed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["round", "field_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["round", "field_type"],
                name="unique_round_answer_field_state",
            )
        ]

    def __str__(self) -> str:
        return f"{self.round} / {self.field_type}"


class AnswerSubmission(models.Model):
    class AnswerType(models.TextChoices):
        TITLE = "title", "Title"
        ARTIST = "artist", "Artist"
        FULL = "full", "Full"

    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name="submissions")
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="answer_submissions",
    )
    answer_raw = models.CharField(max_length=255)
    answer_type = models.CharField(
        max_length=20,
        choices=AnswerType.choices,
        default=AnswerType.FULL,
    )
    normalized_answer = models.CharField(max_length=255, db_index=True)
    is_correct = models.BooleanField(default=False)
    is_accepted = models.BooleanField(default=False)
    score_awarded = models.IntegerField(default=0)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round", "submitted_at"]

    def __str__(self) -> str:
        return f"{self.participant} / {self.answer_type} / {self.answer_raw}"
