from django.db import models
from django.utils import timezone


class ReviewAction(models.Model):
    class Action(models.TextChoices):
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        REQUEST_REVIEW = "request_review", "Request review"
        DISABLE = "disable", "Disable"

    target_type = models.CharField(max_length=100)
    target_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=50, choices=Action.choices)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        related_name="review_actions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"


class QualityReport(models.Model):
    class TargetType(models.TextChoices):
        SONG = "song", "Song"
        YOUTUBE_SOURCE = "youtube_source", "YouTube source"

    class Reason(models.TextChoices):
        WRONG_TITLE = "wrong_title", "Wrong title"
        WRONG_ARTIST = "wrong_artist", "Wrong artist"
        WRONG_AUDIO = "wrong_audio", "Wrong audio"
        UNAVAILABLE = "unavailable", "Unavailable"
        UNOFFICIAL_VIDEO = "unofficial_video", "Unofficial video"
        OTHER = "other", "Other"

    target_type = models.CharField(max_length=30, choices=TargetType.choices)
    song = models.ForeignKey(
        "catalog.Song",
        on_delete=models.CASCADE,
        related_name="quality_reports",
        null=True,
        blank=True,
    )
    youtube_source = models.ForeignKey(
        "catalog.YoutubeSource",
        on_delete=models.CASCADE,
        related_name="quality_reports",
        null=True,
        blank=True,
    )
    reason = models.CharField(max_length=50, choices=Reason.choices, default=Reason.OTHER)
    message = models.TextField(blank=True)
    reporter_fingerprint = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["target_type", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.apply_report_threshold()

    def apply_report_threshold(self) -> None:
        if self.target_type == self.TargetType.SONG and self.song_id:
            song = self.song
            was_playable = not song.blocked
            song.report_count = self.__class__.objects.filter(song=song).count()
            if song.report_count >= 3:
                song.blocked = True
            song.save(update_fields=["report_count", "blocked", "updated_at"])
            if song.report_count >= 3 and was_playable:
                self._return_song_questions_to_review(song)
            return

        if self.target_type == self.TargetType.YOUTUBE_SOURCE and self.youtube_source_id:
            source = self.youtube_source
            was_playable = source.status in {
                source.Status.AUTO_APPROVED,
                source.Status.APPROVED,
            }
            source.report_count = self.__class__.objects.filter(youtube_source=source).count()
            update_fields = ["report_count", "updated_at"]
            if source.report_count >= 3:
                source.status = source.Status.NEEDS_REVIEW
                update_fields.append("status")
            source.save(update_fields=update_fields)
            if source.report_count >= 3 and was_playable:
                self._return_youtube_source_questions_to_review(source)

    def _return_song_questions_to_review(self, song) -> None:
        from apps.quizzes.models import QuizQuestion

        updated_count = QuizQuestion.objects.filter(
            song=song,
            status=QuizQuestion.Status.APPROVED,
        ).update(
            status=QuizQuestion.Status.NEEDS_REVIEW,
            updated_at=timezone.now(),
        )
        ReviewAction.objects.create(
            target_type=self.TargetType.SONG,
            target_id=song.id,
            action=ReviewAction.Action.REQUEST_REVIEW,
            reason="quality_report_threshold",
            metadata={
                "quality_report_id": self.id,
                "report_count": song.report_count,
                "returned_question_count": updated_count,
            },
        )

    def _return_youtube_source_questions_to_review(self, source) -> None:
        from apps.quizzes.models import QuizQuestion

        updated_count = QuizQuestion.objects.filter(
            youtube_source=source,
            status=QuizQuestion.Status.APPROVED,
        ).update(
            status=QuizQuestion.Status.NEEDS_REVIEW,
            updated_at=timezone.now(),
        )
        ReviewAction.objects.create(
            target_type=self.TargetType.YOUTUBE_SOURCE,
            target_id=source.id,
            action=ReviewAction.Action.REQUEST_REVIEW,
            reason="quality_report_threshold",
            metadata={
                "quality_report_id": self.id,
                "report_count": source.report_count,
                "returned_question_count": updated_count,
            },
        )

    def __str__(self) -> str:
        return f"{self.reason} report for {self.target_type}"
