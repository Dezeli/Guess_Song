from django.db import models


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
            song.report_count = self.__class__.objects.filter(song=song).count()
            if song.report_count >= 3:
                song.blocked = True
            song.save(update_fields=["report_count", "blocked", "updated_at"])
            return

        if self.target_type == self.TargetType.YOUTUBE_SOURCE and self.youtube_source_id:
            source = self.youtube_source
            source.report_count = self.__class__.objects.filter(youtube_source=source).count()
            update_fields = ["report_count", "updated_at"]
            if source.report_count >= 3:
                source.status = source.Status.BLOCKED
                update_fields.append("status")
            source.save(update_fields=update_fields)

    def __str__(self) -> str:
        return f"{self.reason} report for {self.target_type}"
